/** Плавно прокручивает к секции; отступ под шапку задаёт scroll-margin-top в стилях */
export function scrollToSection(id: string): void {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/** Сохраняет файл из памяти через временную ссылку <a download> — так скачиваются ответы с токеном */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // Браузер забирает файл не сразу — освобождаем ссылку чуть позже
  setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

/** Копирует текст в буфер обмена; false — браузер не дал (нет HTTPS или прав) */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
