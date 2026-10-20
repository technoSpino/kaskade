// Chunked upload of a big video (follow-up #9): the web server in front of the API aborts
// requests that take longer than 5 minutes, so the file goes up in small pieces. Each piece
// is retried; the server says how much it has, so a lost answer never duplicates data.
import { api } from './api'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function putChunk(uploadId, offset, blob) {
  const res = await fetch(`/api/media/uploads/${uploadId}?offset=${offset}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: blob
  })
  if (!res.ok) throw new Error(`Fehler ${res.status}`)
  return (await res.json()).received
}

/**
 * Upload `file` in chunks; calls onProgress(sentBytes, totalBytes). Returns the uploadId to
 * register with POST /media/upload. `deps` lets tests replace the network calls.
 */
export async function uploadInChunks(file, onProgress = () => {}, deps = {}) {
  const start = deps.start ?? ((body) => api.post('/media/uploads', body))
  const put = deps.put ?? putChunk
  const wait = deps.wait ?? sleep
  const { uploadId, chunkSize } = await start({ filename: file.name, size: file.size })
  let sent = 0
  let failures = 0
  onProgress(0, file.size)
  while (sent < file.size) {
    try {
      sent = await put(uploadId, sent, file.slice(sent, Math.min(file.size, sent + chunkSize)))
      failures = 0
      onProgress(sent, file.size)
    } catch (e) {
      failures++
      if (failures > 5) throw new Error(`Hochladen abgebrochen (${e.message}). Bitte noch einmal versuchen.`)
      await wait(1000 * failures)
    }
  }
  return uploadId
}
