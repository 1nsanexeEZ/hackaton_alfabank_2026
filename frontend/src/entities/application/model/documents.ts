import { clientApi, type DocumentDto } from '@/shared/api'

import { contentTypeOf } from './documentFormats'

/**
 * Документ к заявке: бэкенд выдаёт подписанную ссылку, браузер кладёт файл прямо в хранилище,
 * потом бэкенд подтверждает, что файл дошёл. Так же грузятся документы по дозапросу банка.
 */
export async function uploadApplicationDocument(applicationId: string, type: string, file: File): Promise<DocumentDto> {
  const { document, upload } = await clientApi.requestDocumentUpload(applicationId, {
    type,
    filename: file.name,
    content_type: contentTypeOf(file),
    size_bytes: file.size,
  })
  await clientApi.uploadFile(upload, file)
  return clientApi.confirmDocument(applicationId, document.id)
}
