import { describe, expect, it } from 'vitest'
import { uploadInChunks } from '../../lib/upload'

function fakeServer({ failAt = [] } = {}) {
  const server = { data: '', calls: 0 }
  server.start = async () => ({ uploadId: 'u1', chunkSize: 4 })
  server.put = async (id, offset, blob) => {
    server.calls++
    if (failAt.includes(server.calls)) throw new Error('network')
    if (offset === server.data.length) server.data += await blob.text()
    return server.data.length
  }
  return server
}

describe('chunked upload', () => {
  it('sends the file in chunks and reports progress', async () => {
    const s = fakeServer()
    const progress = []
    const file = new File(['abcdefghij'], 'film.mp4')
    const id = await uploadInChunks(file, (sent, total) => progress.push(`${sent}/${total}`), { start: s.start, put: s.put, wait: async () => {} })
    expect(id).toBe('u1')
    expect(s.data).toBe('abcdefghij')
    expect(progress).toEqual(['0/10', '4/10', '8/10', '10/10'])
  })

  it('retries a failed chunk without duplicating data', async () => {
    const s = fakeServer({ failAt: [2, 3] })
    await uploadInChunks(new File(['abcdefghij'], 'f.mp4'), () => {}, { start: s.start, put: s.put, wait: async () => {} })
    expect(s.data).toBe('abcdefghij')
  })

  it('gives up after repeated failures with a German message', async () => {
    const s = fakeServer({ failAt: [1, 2, 3, 4, 5, 6] })
    await expect(uploadInChunks(new File(['abc'], 'f.mp4'), () => {}, { start: s.start, put: s.put, wait: async () => {} }))
      .rejects.toThrow(/Hochladen abgebrochen/)
  })
})
