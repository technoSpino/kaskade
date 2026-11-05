// Small fetch wrapper for the Kaskade API (proxied under /api).

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(method, path, body) {
  const opts = { method, headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`/api${path}`, opts)
  } catch {
    throw new ApiError('Server nicht erreichbar. Läuft der Dienst kaskade-api?', 0)
  }
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    // e.g. the proxy's HTML error page when kaskade-api is down
    if (res.ok) throw new ApiError('Unerwartete Antwort vom Server.', res.status)
  }
  if (!res.ok) {
    const detail = data && data.detail
    const msg = typeof detail === 'string'
      ? detail
      : res.status >= 500 ? 'Server nicht erreichbar. Läuft der Dienst kaskade-api?' : `Fehler ${res.status}`
    throw new ApiError(msg, res.status)
  }
  return data
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
  put: (path, body) => request('PUT', path, body ?? {}),
  patch: (path, body) => request('PATCH', path, body ?? {}),
  del: (path) => request('DELETE', path)
}
