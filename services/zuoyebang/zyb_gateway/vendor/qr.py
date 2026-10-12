"""本地生成扫码二维码，不把登录挑战交给第三方图像服务。"""
import base64
import io


def qr_data_url(payload):
    try:
        import segno
    except ImportError as exc:
        raise ValueError('扫码登录需要安装 requirements-zuoyebang.txt 中的依赖') from exc
    if not isinstance(payload, str) or not payload or len(payload.encode()) > 2048:
        raise ValueError('二维码内容不合法')
    qr = segno.make(payload, error='m', micro=False, boost_error=False)
    image = io.BytesIO()
    qr.save(image, kind='png', scale=6, border=4)
    return 'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode('ascii')
