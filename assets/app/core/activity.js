/** Remote PIN sessions stay active only after real input, including scroll in nested workspaces. */
export async function startActivityTracking(doc = document, fetchImpl = globalThis.fetch) {
  try {
    const response = await fetchImpl('/api/auth/session');
    const state = await response.json();
    if (!state.remote || !state.authenticated) return false;
    let last = 0;
    const active = () => {
      const now = Date.now();
      if (now - last < 60000) return;
      last = now;
      fetchImpl('/api/auth/activity', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {});
    };
    for (const name of ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']) doc.addEventListener(name, active, { passive: true, capture: true });
    return true;
  } catch (_) { return false; }
}
