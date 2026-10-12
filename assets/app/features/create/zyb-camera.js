/** 网页摄像头：按视频原始尺寸拍照，迟到授权、取帧和离页均校验代次。 */
export function createCamera({ mediaDevices = globalThis.navigator?.mediaDevices, secure = globalThis.isSecureContext,
  video, changed = () => {}, createCanvas = () => document.createElement('canvas') } = {}) {
  let stream = null;
  let generation = 0;
  let pending = false;
  const stopTracks = value => value?.getTracks().forEach(track => track.stop());
  function stop() {
    generation += 1;
    pending = false;
    stopTracks(stream);
    stream = null;
    if (video) { video.srcObject = null; video.hidden = true; }
    changed({ on: false, pending: false, message: '摄像头未开启' });
  }
  async function open() {
    if (pending || stream) return;
    if (!secure || !mediaDevices?.getUserMedia) {
      changed({ on: false, pending: false, message: '摄像头需要 HTTPS 或本机 localhost，请使用安全地址打开' });
      return;
    }
    const token = ++generation;
    pending = true;
    changed({ on: false, pending: true, message: '等待摄像头授权…' });
    try {
      const next = await mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' },
        width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false });
      if (token !== generation) { stopTracks(next); return; }
      stream = next;
      if (video) { video.srcObject = stream; video.hidden = false; await video.play(); }
      if (token !== generation) return;
      pending = false;
      stream.getVideoTracks().forEach(track => track.addEventListener?.('ended', () => { if (token === generation) stop(); }, { once: true }));
      changed({ on: true, pending: false, message: '实时预览 · 后置优先' });
    } catch (error) {
      if (token !== generation) return;
      stopTracks(stream);
      stream = null;
      pending = false;
      if (video) { video.srcObject = null; video.hidden = true; }
      const reason = { NotAllowedError: '未获得摄像头权限，请在浏览器中允许后重试', NotFoundError: '没有找到可用摄像头',
        NotReadableError: '摄像头正在被其它应用使用，请关闭后重试', OverconstrainedError: '当前摄像头不支持请求的模式' };
      changed({ on: false, pending: false, message: reason[error?.name] || '摄像头无法开启，请检查设备后重试' });
    }
  }
  async function capture() {
    if (!stream || pending || !video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      throw new Error('摄像头画面尚未就绪，请稍后拍照');
    }
    const token = generation, canvas = createCanvas();
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    try {
      const context = canvas.getContext('2d');
      if (!context) throw new Error('当前浏览器无法拍照，请切换到上传图片');
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .95));
      if (token !== generation || !stream) throw new Error('拍照已取消，请重新打开摄像头');
      if (!blob?.size) throw new Error('未能生成照片，请重拍或上传图片');
      return blob;
    } finally {
      canvas.width = 0; canvas.height = 0;
    }
  }
  return { open, stop, capture, toggle: () => (stream || pending ? stop() : open()), dispose: stop };
}
