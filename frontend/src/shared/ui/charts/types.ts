/** Сегмент кольца или строка списка-диаграммы; color — CSS-значение, например var(--color-brand) */
export interface ChartSegment {
  label: string
  value: number
  color: string
  /** Пояснение под подписью, например сумма по продукту */
  hint?: string
}

/** Ряд столбчатой диаграммы: по значению на каждую подпись оси */
export interface ChartSeries {
  label: string
  color: string
  values: number[]
}
