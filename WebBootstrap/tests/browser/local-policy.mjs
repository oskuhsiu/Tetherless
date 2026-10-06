// This is an application-request guard, not an operating-system network sandbox.
export function permitsLocalRequest(rawUrl, method, baseURL) {
  try {
    const url = new URL(rawUrl), base = new URL(baseURL);
    if (!['GET', 'HEAD'].includes(method)) return false;
    if (url.protocol === 'blob:') return url.origin === base.origin;
    return url.protocol === 'http:' && url.origin === base.origin &&
      url.pathname.startsWith(base.pathname) && !url.username && !url.password;
  } catch { return false; }
}
