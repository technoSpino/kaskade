import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../../lib/api'

const respond = (status, body) => vi.fn(async () => ({ ok: status < 400, status, text: async () => body }))

describe('api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns parsed JSON', async () => {
    vi.stubGlobal('fetch', respond(200, '{"ok":true}'))
    expect(await api.get('/health')).toEqual({ ok: true })
  })

  it('uses the server detail message on errors', async () => {
    vi.stubGlobal('fetch', respond(404, '{"detail":"Karte nicht gefunden"}'))
    await expect(api.get('/x')).rejects.toThrow('Karte nicht gefunden')
  })

  it('explains a down server behind the proxy (HTML 502)', async () => {
    vi.stubGlobal('fetch', respond(502, '<html>Bad Gateway</html>'))
    await expect(api.get('/x')).rejects.toThrow('kaskade-api')
  })

  it('explains network failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const err = await api.get('/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
  })

  it('rejects non-JSON success responses', async () => {
    vi.stubGlobal('fetch', respond(200, '<html></html>'))
    await expect(api.get('/x')).rejects.toThrow('Unerwartete Antwort')
  })

  it('sends JSON bodies and FormData as-is', async () => {
    const f = respond(200, '{}')
    vi.stubGlobal('fetch', f)
    await api.post('/a', { x: 1 })
    expect(f.mock.calls[0][1].headers['Content-Type']).toBe('application/json')
    const form = new FormData()
    await api.post('/b', form)
    expect(f.mock.calls[1][1].body).toBe(form)
  })
})
