/** 网页摄像头：仅实时预览，迟到授权和离页都停止全部 tracks。 */
export function createCamera({ mediaDevices = globalThis.navigator?.mediaDevices, secure = globalThis.isSecureContext,
  video, changed = () => {} } = {}) {
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
      const next = await mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      if (token !== generation) { stopTracks(next); return; }
      stream = next;
      if (video) { video.srcObject = stream; video.hidden = false; await video.play(); }
      if (token !== generation) return;
      pending = false;
      stream.getVideoTracks().forEach(track => track.addEventListener?.('ended', stop, { once: true }));
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
  return { open, stop, toggle: () => (stream || pending ? stop() : open()), dispose: stop };
}
