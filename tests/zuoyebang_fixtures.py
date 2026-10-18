"""纯合成作业帮候选，不含用户题库或任何真实会话。"""
import base64
import io
from PIL import Image, ImageDraw
from omrs.zuoyebang.direct import SEARCH_URL


def profile():
    return {'url': SEARCH_URL, 'session_token': 'synthetic-signing-seed',
            'fields': {'cuid': 'synthetic-enrolled-device', 'vc': '1', 'vcname': 'fixture', 'ZYBUSS': 'synthetic-account'},
            'headers': {'Cookie': 'ZYBUSS=synthetic-account'}}


def png(kind='triangle'):
    image = Image.new('RGB', (420, 240) if kind == 'triangle' else (400, 50), 'white')
    draw = ImageDraw.Draw(image)
    if kind == 'triangle':
        draw.line([(210, 25), (35, 210), (385, 210), (210, 25)], fill='black', width=4)
        draw.line([(210, 25), (210, 210)], fill='black', width=2)
        for point, label in [((210, 5), 'A'), ((20, 212), 'B'), ((385, 212), 'C'), ((215, 212), 'D')]:
            draw.text(point, label, fill='black')
    else:
        draw.text((20, 15), 'AD = sqrt(25 - 9) = 4', fill='black')
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def data_url(kind='triangle'):
    return 'data:image/png;base64,' + base64.b64encode(png(kind)).decode()


def svg():
    """合成的路径公式，覆盖旧题库声明与图片内部的字形引用。"""
    return b'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
        width="60" height="14" viewBox="0 0 60 14" version="1.0"
        contentScriptType="text/ecmascript" contentStyleType="text/css" zoomAndPan="magnify"
        font-family="Dialog" font-size="12" fill-opacity="1" stroke-dasharray="none"
        shape-rendering="auto" color-rendering="auto" image-rendering="auto"
        color-interpolation="auto" text-rendering="auto" preserveAspectRatio="xMidYMid meet">
        <defs id="genericDefs"><path id="minus" d="M0 0H8V2H0Z"/></defs>
        <g transform="translate(2,6)" fill="#cc0000" stroke="none">
            <use xlink:href="#minus"/><use href="#minus" x="14"/>
            <path d="M28 -4H36V6H28ZM42 -4H50V6H42Z"/>
        </g></svg>'''


def candidates():
    answer = '<p>第1步：等腰三角形顶角的角平分线也是底边上的高和中线。</p>'
    answer += r'<p>因为 $AB=AC=5$，$BC=6$，所以 $BD=DC=3$。</p>'
    answer += '<p><img src="' + data_url('formula') + '" alt="图片形式的公式"></p>'
    answer += r'<p>由勾股定理，$AD=\sqrt{AB^2-BD^2}=\sqrt{25-9}=4$。</p>'
    answer += ''.join(r'<p>原解析步骤 %d：保留推理顺序与公式 $S=\frac{1}{2}BC\cdot AD=12$。</p>' % i for i in range(1, 56))
    answer += '<p><strong>解析末尾：AD=4，三角形ABC的面积为12。</strong></p>'
    return [
        {'location_index': 0, 'queryInfo': {'resultIndex': 0, 'matchType': 'candidate'},
         'question': {'content': r'<p>如图，等腰三角形 $AB=AC=5$，$BC=6$。求高 $AD$ 和面积。</p><p><img src="' + data_url() + '" alt="等腰三角形附图"></p>', 'picList': []},
         'answer': [{'content': answer, 'picList': []}]},
        {'location_index': 0, 'question': {'content': '<p>候选二：计算 $2+3$。</p>'}, 'answer': [{'content': '<p>候选二答案：5。</p>'}]},
        {'location_index': 1, 'question': {'content': '<p>位置二：求 $x^2=4$ 的解。</p>'}, 'answer': []},
    ]
