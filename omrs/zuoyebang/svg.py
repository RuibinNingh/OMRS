"""验证静态 SVG 附图；原字节仅供 Chromium 的图片上下文读取。"""
import math
import re
from xml.etree import ElementTree as ET
from .store import ZybError

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
XML = 'http://www.w3.org/XML/1998/namespace'
MAX_NODES = 10_000
MAX_DEPTH = 64
MAX_EXPANDED_NODES = 50_000
PIXELS = 40_000_000
TAGS = frozenset('{' + SVG + '}' + tag for tag in '''svg g defs path rect circle ellipse line polyline polygon
    text tspan title desc use symbol clipPath mask linearGradient radialGradient stop'''.split())
PRESENTATION = frozenset('''fill fill-opacity fill-rule stroke stroke-width stroke-opacity
    stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset
    opacity color color-interpolation color-rendering shape-rendering text-rendering
    image-rendering font-family font-size font-style font-weight font-variant font-stretch
    letter-spacing word-spacing text-anchor text-decoration dominant-baseline
    alignment-baseline baseline-shift clip-path clip-rule mask visibility display stop-color stop-opacity'''.split())
ATTRIBUTES = PRESENTATION | frozenset('''id version contentScriptType contentStyleType zoomAndPan
    x y x1 y1 x2 y2 dx dy cx cy r rx ry width height viewBox preserveAspectRatio
    d points transform rotate textLength lengthAdjust pathLength
    gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity
    fx fy fr clipPathUnits maskUnits maskContentUnits'''.split())
ID = r'[A-Za-z_][A-Za-z0-9_.:-]*'
LOCAL_URL = re.compile(r'url\(\s*([\'"]?)#(' + ID + r')\1\s*\)', re.I)
LENGTH = re.compile(r'([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(px|pt|pc|in|cm|mm|q)?', re.I)
UNITS = {'px': 1, 'pt': 4 / 3, 'pc': 16, 'in': 96, 'cm': 96 / 2.54, 'mm': 96 / 25.4, 'q': 96 / 101.6}


def _unsupported():
    raise ZybError('SVG 附图含不支持的内容、外部资源或循环引用，原内容已保留', 'image_invalid')


class _Tree(ET.TreeBuilder):
    """在解析期间限制树规模，并在实体展开前拒绝 DTD。"""
    def __init__(self):
        super().__init__()
        self.depth = self.nodes = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise ZybError('SVG 附图结构超过渲染资源预算，原内容已保留', 'render_resource', 422)
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)

    def doctype(self, *_args):
        _unsupported()

    def pi(self, *_args):
        _unsupported()


def _dimension(value):
    match = LENGTH.fullmatch(value.strip())
    if not match:
        raise ValueError('尺寸不是绝对长度')
    return float(match[1]) * UNITS.get((match[2] or 'px').lower(), 1)


def _dimensions(root):
    try:
        box = re.split(r'[\s,]+', root.get('viewBox', '').strip())
        if root.get('viewBox') is not None:
            box = list(map(float, box))
            if len(box) != 4 or not all(map(math.isfinite, box)) or min(box[2:]) <= 0:
                raise ValueError('视口不合法')
        width = _dimension(root.attrib['width']) if 'width' in root.attrib else float(box[2])
        height = _dimension(root.attrib['height']) if 'height' in root.attrib else float(box[3])
        if not all(math.isfinite(value) and value > 0 for value in (width, height)) or width * height > PIXELS:
            raise ValueError('尺寸超限')
    except (ValueError, IndexError, OverflowError) as exc:
        raise ZybError('SVG 附图尺寸不合法或超过像素预算，原内容已保留', 'image_invalid') from exc


def _value(value, references):
    # 不允许 CSS 转义、注释或声明嵌套，URL 只接受当前图片内的片段。
    if any(part in value for part in ('\\', '/*', '@', '{', '}')):
        _unsupported()
    if re.search(r'url\s*\(', value, re.I):
        match = LOCAL_URL.fullmatch(value.strip())
        if not match:
            _unsupported()
        references.append(match[2])


def _attributes(element, ids):
    references = []
    for name, value in element.attrib.items():
        if name == 'id':
            if not re.fullmatch(ID, value) or value in ids:
                _unsupported()
            ids[value] = element
        elif name in ('href', '{' + XLINK + '}href'):
            if not re.fullmatch('#' + ID, value):
                _unsupported()
            references.append(value[1:])
        elif name == 'style':
            for declaration in value.split(';'):
                if not declaration.strip():
                    continue
                prop, separator, content = declaration.partition(':')
                if not separator or prop.strip().lower() not in PRESENTATION or not content.strip():
                    _unsupported()
                _value(content, references)
        elif name not in ATTRIBUTES and name not in ('{' + XML + '}lang', '{' + XML + '}space'):
            _unsupported()
        if name != 'style':
            _value(value, references)
    return references


def _references(root, ids, references):
    memo, visiting = {}, set()

    def size(element, depth=0):
        if depth >= MAX_DEPTH or element in visiting:
            _unsupported()
        if element in memo:
            return memo[element]
        visiting.add(element)
        total, height = 1, 1
        targets = []
        for identity in references[element]:
            if identity not in ids:
                _unsupported()
            targets.append(ids[identity])
        for child in [*element, *targets]:
            count, child_height = size(child, depth + 1)
            total += count
            height = max(height, child_height + 1)
            if total > MAX_EXPANDED_NODES or height > MAX_DEPTH:
                raise ZybError('SVG 附图引用超过渲染资源预算，原内容已保留', 'render_resource', 422)
        visiting.remove(element)
        memo[element] = total, height
        return memo[element]

    size(root)


def validate(raw):
    """不改写或删减视觉内容；不能完整静态渲染时明确拒绝。"""
    try:
        root = ET.fromstring(raw, parser=ET.XMLParser(target=_Tree()))
    except ZybError:
        raise
    except (ET.ParseError, ValueError) as exc:
        raise ZybError('附图无法解码，原内容已保留', 'image_invalid') from exc
    if root.tag != '{' + SVG + '}svg':
        raise ZybError('附图无法解码，原内容已保留', 'image_invalid')
    _dimensions(root)
    ids, references = {}, {}
    for element in root.iter():
        if element.tag not in TAGS:
            _unsupported()
        references[element] = _attributes(element, ids)
    _references(root, ids, references)
