"""题目静态配图：90mm双栏规范、不可覆盖附件及AI用PNG派生图。"""
import base64
import hashlib
import math
import os
import re
import signal
from functools import lru_cache
import subprocess
import sys
from threading import BoundedSemaphore
from xml.etree import ElementTree as ET

from .zuoyebang import svg as safety

MIME = 'image/svg+xml'
MAX_BYTES = 256 * 1024
PRINT_MM = 90
MM = 96 / 25.4
MANAGED = re.compile(r'OP-[0-9]+-svg-([0-9a-f]{64})\.svg\Z')
_NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
_TRANSFORM = re.compile(r'\s*(translate|scale|rotate|matrix)\s*\(([^)]*)\)\s*[,\s]*')
_PNG_SLOTS = BoundedSemaphore(2)


def is_svg(raw):
    return isinstance(raw, bytes) and raw.lstrip(b'\xef\xbb\xbf \t\r\n').startswith(b'<')


def _style(element, inherited):
    result = {**inherited, **element.attrib}
    for declaration in element.get('style', '').split(';'):
        if declaration.strip():
            key, _, value = declaration.partition(':')
            result[key.strip().lower()] = value.strip()
    return result


def _multiply(a, b):
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3])


def _transform(value):
    matrix = (1., 0., 0., 1.)
    rest = value.strip()
    while rest:
        match = _TRANSFORM.match(rest)
        if not match:
            raise ValueError('SVG只支持translate、scale、rotate和matrix静态变换')
        kind, source = match.groups()
        if re.sub(_NUMBER + r'|[\s,]', '', source):
            raise ValueError('SVG变换参数不合法')
        nums = [float(v) for v in re.findall(_NUMBER, source)]
        if not all(math.isfinite(v) and abs(v) <= 1e6 for v in nums):
            raise ValueError('SVG变换参数超限')
        if kind == 'translate' and len(nums) in (1, 2):
            local = (1., 0., 0., 1.)
        elif kind == 'scale' and len(nums) in (1, 2):
            local = (nums[0], 0., 0., nums[-1])
        elif kind == 'rotate' and len(nums) in (1, 3):
            angle = math.radians(nums[0])
            local = (math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle))
        elif kind == 'matrix' and len(nums) == 6:
            local = tuple(nums[:4])
        else:
            raise ValueError('SVG变换参数数量不正确')
        matrix = _multiply(matrix, local)
        rest = rest[match.end():]
    return matrix


def _minimum_scale(matrix):
    a, b, c, d = matrix
    total = a*a+b*b+c*c+d*d
    determinant = (a*d-b*c)**2
    largest = (total + math.sqrt(max(0., total*total-4*determinant))) / 2
    return math.sqrt(determinant / largest) if largest else 0.


def inspect(raw, *, print_mm=PRINT_MM):
    """先复用完整静态安全检查，再检查可测的纸面尺寸；不宣称语义或遮挡已通过。"""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('SVG配图须为1字节至256KiB，请简化图形')
    safety.validate(raw)
    root = ET.fromstring(raw)
    if len(list(root.iter())) > 1000:
        raise ValueError('SVG配图超过1000个节点，请简化或拆图')
    try:
        box = [float(v) for v in re.split(r'[\s,]+', root.attrib['viewBox'].strip())]
        if len(box) != 4 or min(box[2:]) <= 0:
            raise ValueError()
        width = safety._dimension(root.get('width', str(box[2])))
        height = safety._dimension(root.get('height', str(box[3])))
        if abs(width / height - box[2] / box[3]) > .001:
            raise ValueError()
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise ValueError('SVG须有有效viewBox，width/height须与其保持相同比例') from exc
    if root.get('preserveAspectRatio', 'xMidYMid meet') not in ('xMidYMid meet', 'xMidYMid'):
        raise ValueError('SVG须等比例显示，不允许裁剪或拉伸')
    if root.get('transform'):
        raise ValueError('SVG根节点不能变换，请只变换白底以外的图形')
    printed_height = print_mm * box[3] / box[2]
    if printed_height > 90 + .01:
        raise ValueError(f'SVG按{print_mm:g}mm栏宽打印高{printed_height:.1f}mm，超过90mm，请拆成多图')
    # 将白底纳入附件本体，Obsidian深浅主题及离线打印都不依赖宿主CSS。
    visible = [child for child in root if child.tag.rsplit('}', 1)[-1] not in ('title', 'desc', 'defs')]
    background = visible[0] if visible else None
    try:
        props = _style(background, {}) if background is not None else {}
        white = props.get('fill', '').lower() in ('white', '#fff', '#ffffff')
        cover = (background is not None and background.tag == '{'+safety.SVG+'}rect'
                 and not background.get('transform') and not background.get('style')
                 and all(float(background.get(k, '0')) == 0 for k in ('rx', 'ry'))
                 and all(float(background.get(k, '0')) == v for k, v in zip(('x', 'y', 'width', 'height'), box))
                 and all(background.get(k, '1') == '1' for k in ('opacity', 'fill-opacity')))
        if not white or not cover:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise ValueError('SVG首个图形须为铺满viewBox的白底rect，保证深色主题可读') from exc
    title = root.find('{'+safety.SVG+'}title')
    title = ''.join(title.itertext()).strip() if title is not None else ''
    if not title or len(title) > 80 or any(ord(c) < 32 for c in title):
        raise ValueError('SVG须有1至80字的title，简要说明配图用途')
    sizes, strokes, labels, shapes = [], [], [], []
    print_scale = print_mm * MM / box[2] * .75

    def visit(element, inherited, matrix, depth=0):
        tag = element.tag.rsplit('}', 1)[-1]
        if depth > 24:
            raise ValueError('SVG配图嵌套超过24层，请简化')
        if (tag in ('use', 'symbol', 'clipPath', 'mask') or (tag == 'svg' and element is not root)
                or any(k in element.attrib for k in ('textLength', 'lengthAdjust', 'pathLength'))):
            raise ValueError('题目SVG不支持引用复用、遮罩、裁剪或文字压缩，请展开为简单图形')
        # transform不继承；呈现属性按SVG继承后检查，覆盖style内同名属性。
        local = _multiply(matrix, _transform(element.get('transform', '')))
        if not all(math.isfinite(v) and abs(v) <= 1e6 for v in local):
            raise ValueError('SVG叠加变换超限，请展开为简单图形')
        props = _style(element, inherited)
        if any(props.get(key, 'none') != 'none' for key in ('clip-path', 'mask')):
            raise ValueError('题目SVG不支持遮罩或裁剪，请保留完整图形')
        for key in ('display', 'visibility', 'opacity', 'fill-opacity', 'stroke-opacity'):
            if key in props and props[key] not in ('inline', 'visible', '1', '1.0'):
                raise ValueError('题目SVG不支持隐藏或半透明内容，请用清晰的实色图形')
        scale = _minimum_scale(local) * print_scale
        if props.get('font-stretch', 'normal') != 'normal':
            raise ValueError('SVG文字不允许压缩字形，请使用正常字宽')
        for key in ('letter-spacing', 'word-spacing'):
            if props.get(key, 'normal') != 'normal':
                safety._dimension(props[key])  # 仅接受非负绝对间距，拒绝负字距压缩。

        def check_text(value):
            if not (value or '').strip():
                return
            font = safety._dimension(props.get('font-size', '16')) * scale
            if not math.isfinite(font) or font < 8.5 - .001:
                raise ValueError(f'SVG文字按{print_mm:g}mm栏宽仅{font:.1f}pt，须至少8.5pt，请放大文字或拆图')
            sizes.append(font)
            labels.append(value.strip())

        if tag in ('text', 'tspan'):
            check_text(element.text)
            for child in element:
                check_text(child.tail)
        if tag in ('path', 'line', 'polyline', 'polygon', 'rect', 'circle', 'ellipse'):
            shapes.append(tag)
            if props.get('stroke', 'none').lower() != 'none':
                stroke = safety._dimension(props.get('stroke-width', '1')) * scale
                if not math.isfinite(stroke) or stroke < .5 - .001:
                    raise ValueError(f'SVG线条按{print_mm:g}mm栏宽仅{stroke:.2f}pt，须至少0.5pt')
                strokes.append(stroke)
        inherited_props = {k: v for k, v in props.items() if k in safety.PRESENTATION}
        for child in element:
            visit(child, inherited_props, local, depth+1)

    visit(root, {}, (1., 0., 0., 1.))
    warnings = []
    if printed_height > 70:
        warnings.append('图高超过70mm，建议精简或拆图')
    if len(labels) > 12 or sum(map(len, labels)) > 100:
        warnings.append('图内标注较多，建议把完整解释移到正文')
    if len(shapes) > 40:
        warnings.append('图形较多，请在双栏预览中核对密度')
    return {'mime': MIME, 'width': width, 'height': height, 'title': title,
            'sha256': hashlib.sha256(raw).hexdigest(), 'print_width_mm': print_mm,
            'print_height_mm': round(printed_height, 2), 'min_font_pt': min(sizes, default=None),
            'min_stroke_pt': min(strokes, default=None), 'warnings': warnings}


def name_for(question_id, raw):
    if not re.fullmatch(r'OP-[0-9]+', question_id):
        raise ValueError('SVG附件须绑定稳定题目身份')
    return question_id + '-svg-' + hashlib.sha256(raw).hexdigest() + '.svg'


def verify_name(name, raw):
    match = MANAGED.fullmatch(os.path.basename(name))
    if match and match[1] != hashlib.sha256(raw).hexdigest():
        raise ValueError('SVG附件已被同名修改，请保存为新附件并更新正文引用')


def save(vault, question_id, raw):
    """相同内容复用；有变化生成新名；安全目录描述符下原子发布，绝不覆盖原件。"""
    from .question_images import _DIRECTORY_FDS, _directory, _open_image, _read_bytes
    from .common import QUESTIONS_DIR, ATTACHMENTS_DIR
    info = inspect(raw)
    name = name_for(question_id, raw)
    if not _DIRECTORY_FDS:
        _save_from_paths(vault, name, raw)
        return name, info
    with _directory(os.path.abspath(vault)) as base, _directory(QUESTIONS_DIR, base) as questions:
        try:
            os.mkdir(ATTACHMENTS_DIR, dir_fd=questions)
        except FileExistsError:
            pass
        with _directory(ATTACHMENTS_DIR, questions) as attachments:
            try:
                descriptor = _open_image(name, attachments)
            except FileNotFoundError:
                temp_name = '.svg-' + os.urandom(16).hex()
                descriptor = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=attachments)
                try:
                    with os.fdopen(descriptor, 'wb') as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        os.link(temp_name, name, src_dir_fd=attachments, dst_dir_fd=attachments, follow_symlinks=False)
                    except FileExistsError:
                        descriptor = _open_image(name, attachments)
                        try:
                            if _read_bytes(descriptor, MAX_BYTES) != raw:
                                raise ValueError('SVG已有不同内容，不能覆盖')
                        finally:
                            os.close(descriptor)
                    os.fsync(attachments)
                finally:
                    os.unlink(temp_name, dir_fd=attachments)
            else:
                try:
                    if _read_bytes(descriptor, MAX_BYTES) != raw:
                        raise ValueError('SVG已有不同内容，不能覆盖')
                finally:
                    os.close(descriptor)
    return name, info


def _save_from_paths(vault, name, raw):
    """无目录FD的平台仍逐层拒绝重解析点，核对身份并以硬链接原子发布。"""
    import stat
    from .common import QUESTIONS_DIR, ATTACHMENTS_DIR
    from .question_images import _linked, _identity, _open_image, _read_bytes
    base = os.path.abspath(vault)
    questions = os.path.join(base, QUESTIONS_DIR)
    attachments = os.path.join(questions, ATTACHMENTS_DIR)
    directories = {}

    def check(path):
        info = os.lstat(path)
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError('SVG附件目录不是安全的普通目录')
        identity = _identity(info)
        if path in directories and directories[path] != identity:
            raise ValueError('SVG附件目录在保存期间变化，请重试')
        directories[path] = identity

    for path in (base, questions):
        check(path)
    try:
        os.mkdir(attachments)
    except FileExistsError:
        pass
    check(attachments)
    target = os.path.join(attachments, name)
    temp = os.path.join(attachments, '.svg-' + os.urandom(16).hex())
    try:
        with open(temp, 'xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        for path in directories:
            check(path)
        try:
            os.link(temp, target)
        except FileExistsError:
            pass
        descriptor = _open_image(target)
        try:
            if _read_bytes(descriptor, MAX_BYTES) != raw:
                raise ValueError('SVG已有不同内容，不能覆盖')
        finally:
            os.close(descriptor)
        for path in directories:
            check(path)
    finally:
        # 目录已被替换时不沿新路径删除文件。
        if all(_identity(os.lstat(path)) == identity and not _linked(os.lstat(path))
               for path, identity in directories.items()):
            os.unlink(temp)


@lru_cache(maxsize=8)
def to_png(raw):
    """独立进程限制转换总时间；原SVG不改写，失败明确报告。"""
    inspect(raw)
    if not _PNG_SLOTS.acquire(timeout=30):
        raise ValueError('SVG转PNG忙碌，请稍后重试')
    try:
        with subprocess.Popen([sys.executable, '-m', 'omrs.question_svg'], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name != 'nt',
                              cwd=os.path.dirname(os.path.dirname(__file__))) as process:
            try:
                output, _ = process.communicate(raw, timeout=30)
            except subprocess.TimeoutExpired as exc:
                _stop_renderer(process)
                process.communicate()
                raise ValueError('SVG转PNG超时，请简化图形或重试') from exc
            if process.returncode or not output.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('SVG转PNG失败，请安装Playwright及Chromium；SVG原件已保留')
            return output
    finally:
        _PNG_SLOTS.release()


def _stop_renderer(process):
    """超时后连同Chromium子进程一起结束，避免只杀Python留下浏览器。"""
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
    else:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def for_model(value):
    if isinstance(value, str) and value.startswith('data:' + MIME + ';base64,'):
        encoded = value.partition(',')[2]
        if len(encoded) > (MAX_BYTES + 2) // 3 * 4:
            raise ValueError('SVG配图超过256KiB')
        raw = base64.b64decode(encoded, validate=True)
        return 'data:image/png;base64,' + base64.b64encode(to_png(raw)).decode('ascii')
    return value


def _render(raw):
    from playwright.sync_api import sync_playwright
    info = inspect(raw)
    width = round(PRINT_MM * MM)
    height = math.ceil(width * info['height'] / info['width'])
    src = 'data:' + MIME + ';base64,' + base64.b64encode(raw).decode('ascii')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=3)
            context.route('**/*', lambda route: route.abort())
            page = context.new_page()
            page.set_content('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'
                             '<style>body{margin:0;background:white}img{display:block;width:100%;height:auto}</style>'
                             '<img src="' + src + '">')
            page.locator('img').evaluate('(img) => img.decode()')
            return page.screenshot(type='png', animations='disabled')
        finally:
            browser.close()


if __name__ == '__main__':
    def _terminate(_signum, _frame):
        # 先让Playwright上下文关闭浏览器，主进程仍有强制结束进程组的兜底。
        raise SystemExit(1)
    signal.signal(signal.SIGTERM, _terminate)
    sys.stdout.buffer.write(_render(sys.stdin.buffer.read(MAX_BYTES + 1)))
