import { pdfUrl } from './urls'

// Origin координатора тем же трюком, что в pdfMeta.js: как бы ни строился
// базовый URL в urls.js, /audio окажется на том же хосте, что и /pdfs.
export function serverOrigin(serverHost) {
  return pdfUrl('x.pdf', serverHost).replace(/\/pdfs\/x\.pdf(\?.*)?$/, '')
}