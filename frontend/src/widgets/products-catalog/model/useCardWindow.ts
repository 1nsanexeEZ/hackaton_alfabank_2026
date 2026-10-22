import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

/** Размеры как в ProductFlexCard на десктопе: свёрнутая полоска 5.5rem, зазор 1rem; контенту раскрытой нужно 30rem */
const STRIP_REM = 5.5
const GAP_REM = 1
const EXPANDED_MIN_REM = 30

/**
 * Окно десктопного ряда: раскрытая карточка не уже 30rem, рядом — столько полосок, сколько влезает,
 * остальные за краем. Окно сдвигается ровно настолько, чтобы раскрытая карточка оставалась видна.
 */
export function useCardWindow(viewport: Ref<HTMLElement | undefined>, count: () => number, activeIndex: () => number) {
  const width = ref(0)
  const rem = ref(16)
  const start = ref(0)

  const step = computed(() => (STRIP_REM + GAP_REM) * rem.value)
  const strips = computed(() =>
    Math.max(0, Math.floor((width.value - (EXPANDED_MIN_REM - GAP_REM) * rem.value) / step.value)),
  )
  /** Сколько карточек видно: раскрытая и полоски рядом */
  const size = computed(() => Math.min(count(), strips.value + 1))
  const expandedWidth = computed(() => Math.max(width.value - (size.value - 1) * step.value, 0))

  /*
   * Окно сдвигается минимально, но раскрытая не встаёт к краю, за которым есть ещё продукты:
   * рядом с ней остаётся полоска — затухание края ложится на неё, а не на раскрытую.
   */
  watch(
    [activeIndex, size, count],
    () => {
      const active = Math.max(activeIndex(), 0)
      const margin = size.value >= 3 ? 1 : 0
      const before = active > 0 ? margin : 0
      const after = active < count() - 1 ? margin : 0
      const next = Math.min(Math.max(start.value, active + after - size.value + 1), active - before)
      start.value = Math.max(0, Math.min(next, count() - size.value))
    },
    { immediate: true },
  )

  const offset = computed(() => start.value * step.value)
  const inWindow = (index: number) => index >= start.value && index < start.value + size.value
  const hasBefore = computed(() => start.value > 0)
  const hasAfter = computed(() => start.value + size.value < count())

  let observer: ResizeObserver | undefined

  onMounted(() => {
    rem.value = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
    const measure = () => (width.value = viewport.value?.clientWidth ?? 0)
    measure()
    if ('ResizeObserver' in window && viewport.value) {
      observer = new ResizeObserver(measure)
      observer.observe(viewport.value)
    }
  })

  onBeforeUnmount(() => observer?.disconnect())

  return { offset, expandedWidth, inWindow, hasBefore, hasAfter }
}
