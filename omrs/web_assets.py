"""公网首屏资源：内容版本、原生模块预加载、样式合并和有界 gzip 缓存。"""
import functools
import gzip
import hashlib
import html
import pathlib
import posixpath
import re
import threading
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
PREFIX = "/assets/_v/"
_GENERATOR_HASH = hashlib.sha256(pathlib.Path(__file__).read_bytes()).digest()
TEXT_TYPES = {"text/css", "text/html", "application/javascript", "application/json", "image/svg+xml"}
_HTML_URL = re.compile(r'\b(?:href|src)=(\x22|\x27)(/?assets/[^\x22\x27]+)\1')
_MODULE = re.compile(r'<script\b[^>]*type=[\x22\x27]module[\x22\x27][^>]*src=[\x22\x27]([^\x22\x27]+)')
_IMPORT = re.compile(r'^\s*(?:import\s+(?:[^;]*?\bfrom\s+)?|export\s+[^;]*?\bfrom\s+)[\x22\x27](\.[^\x22\x27]+)[\x22\x27]', re.M)
_CSS_IMPORT = re.compile(r'@import\s+url\([\x22\x27]([^\x22\x27]+)[\x22\x27]\)\s*(?:layer\(([\w.-]+)\))?\s*;')
_CSS_URL = re.compile(r'url\(\s*([\x22\x27]?)([^)\x22\x27]+)\1\s*\)')


def accepts_gzip(value):
    """显式 gzip 优先于 *；q=0 和非法质量值不启用压缩。"""
    encodings = {}
    for item in (value or "").lower().split(","):
        name, *params = item.strip().split(";")
        quality = 1.0
        for param in params:
            key, sep, raw = param.strip().partition("=")
            if key == "q" and sep:
                try:
                    quality = float(raw)
                except ValueError:
                    quality = 0.0
        encodings[name] = 0.0 < quality <= 1.0
    return encodings.get("gzip", encodings.get("*", False))


@functools.lru_cache(maxsize=128)
def compressed(body):
    """仅供最多 128 份、每份不超过 256KiB 的静态文本使用。"""
    return gzip.compress(body, compresslevel=6, mtime=0)


class AssetStore:
    """HTML 请求复核资源内容；同内容跨进程保持同版本。"""
    def __init__(self, root=ROOT):
        self.root = pathlib.Path(root).resolve()
        self.lock = threading.RLock()
        self.signature = None
        self.version = ""
        self.files = {}
        self.styles = {}
        self.preloads = {}

    def refresh(self):
        with self.lock:
            files = {}
            for path in sorted((self.root / "assets").rglob("*")):
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(self.root / "assets"):
                    files[path.relative_to(self.root).as_posix()] = hashlib.sha256(path.read_bytes()).digest()
            signature = tuple(files.items())
            if signature != self.signature:
                digest = hashlib.sha256(b"omrs-web-assets-1\0" + _GENERATOR_HASH)
                for name in files:
                    digest.update(name.encode() + b"\0")
                    digest.update(files[name])
                self.version = digest.hexdigest()[:24]
                self.files = files
                self.signature = signature
                self.styles.clear()
                self.preloads.clear()
            return self.version

    def url(self, name):
        return PREFIX + self.version + "/" + name.removeprefix("assets/")

    def resolve(self, path):
        """保留旧 /assets/ 地址；版本地址必须匹配当前文件快照。"""
        decoded = urllib.parse.unquote(path)
        versioned = decoded.startswith(PREFIX)
        if versioned:
            version, sep, rest = decoded[len(PREFIX):].partition("/")
            if not self.version:
                self.refresh()
            if not sep or version != self.version:
                return None
            decoded = "/assets/" + rest
        name = posixpath.normpath(decoded.lstrip("/"))
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root / "assets") or not target.is_file():
            return None
        if versioned and self.files.get(name) != hashlib.sha256(target.read_bytes()).digest():
            return None
        return target, name, versioned

    def document(self, body):
        with self.lock:
            self.refresh()
            text = body.decode("utf-8")
            modules = [urllib.parse.urlsplit(m).path.lstrip("/") for m in _MODULE.findall(text)]
            text = _HTML_URL.sub(lambda m: m.group(0).replace(m.group(2), self.url(urllib.parse.urlsplit(m.group(2)).path.lstrip("/"))), text)
            links = []
            for module in modules:
                for name in self.module_graph(module):
                    links.append(f'<link rel="modulepreload" href="{html.escape(self.url(name), quote=True)}">')
            return text.replace("</head>", "\n".join(links) + "\n</head>").encode("utf-8")

    def module_graph(self, entry):
        if entry in self.preloads:
            return self.preloads[entry]
        seen, queue = set(), [entry]
        while queue:
            name = queue.pop(0)
            if name in seen or name not in self.files:
                continue
            seen.add(name)
            source = (self.root / name).read_text(encoding="utf-8-sig")
            for specifier in _IMPORT.findall(source):
                child = posixpath.normpath(posixpath.join(posixpath.dirname(name), specifier))
                queue.append(child)
        self.preloads[entry] = tuple(sorted(seen - {entry}))
        return self.preloads[entry]

    def stylesheet(self, name):
        """只合并版本化主样式入口；顺序、@layer 和相对字体地址保持。"""
        with self.lock:
            if name not in self.styles:
                self.styles[name] = self._css(name, set()).encode("utf-8")
            return self.styles[name]

    def _css(self, name, stack):
        if name in stack or name not in self.files:
            raise ValueError("样式依赖缺失或循环")
        stack = stack | {name}
        resource = self.resolve(self.url(name))
        if resource is None:
            raise FileNotFoundError("样式依赖已变化，请刷新页面")
        text = resource[0].read_text(encoding="utf-8-sig")
        # 先改写本文件资源，再展开依赖，防止二次改写子文件的地址。
        def resource(match):
            value = match.group(2).strip()
            if value.startswith(("/", "#", "data:")) or urllib.parse.urlsplit(value).scheme:
                return match.group(0)
            resource_name = posixpath.normpath(posixpath.join(posixpath.dirname(name), value))
            return 'url("' + self.url(resource_name) + '")'
        # import 保留给递归展开，url() 只处理其它声明。
        imports = {}
        def placeholder(match):
            marker = f"/* omrs-import-{len(imports)} */"
            child = posixpath.normpath(posixpath.join(posixpath.dirname(name), match.group(1)))
            imports[marker] = (child, match.group(2))
            return marker
        text = _CSS_IMPORT.sub(placeholder, text)
        text = _CSS_URL.sub(resource, text)
        for marker, (child, layer) in imports.items():
            content = self._css(child, stack)
            text = text.replace(marker, f"@layer {layer} {{\n{content}\n}}" if layer else content)
        return text


ASSETS = AssetStore()
