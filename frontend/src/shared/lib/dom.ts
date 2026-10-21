/** Плавно прокручивает к секции; отступ под шапку задаёт scroll-margin-top в стилях */
export function scrollToSection(id: string): void {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
