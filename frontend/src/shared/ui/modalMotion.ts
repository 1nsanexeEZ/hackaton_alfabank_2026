/**
 * Как окна сайта сменяют друг друга. Одно окно закрылось, а другое открылось в тот же кадр
 * («Мои заявки» → карточка, вход → мастер заявки) — это переход, а не два отдельных события:
 * затемнение остаётся одно и не моргает, старое окно уходит влево, новое приходит справа.
 * Окна не знают друг о друге, поэтому сверяются по времени последнего входа и ухода.
 */
const SWAP_WINDOW_MS = 120

let lastEnter = Number.NEGATIVE_INFINITY
let lastLeave = Number.NEGATIVE_INFINITY

export function markModalEnter(): void {
  lastEnter = performance.now()
}

export function markModalLeave(): void {
  lastLeave = performance.now()
}

/** Открываемся, пока другое окно уходит: затемнение уже есть, своё не проявляем */
export const isSwapIn = () => performance.now() - lastLeave < SWAP_WINDOW_MS

/** Уходим, пока открывается другое окно: своё затемнение гасим сразу, под ним уже новое */
export const isSwapOut = () => performance.now() - lastEnter < SWAP_WINDOW_MS

export const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/** Уже sm (40rem) окно — шторка снизу: въезжает и уезжает по вертикали */
export const isSheet = () => !(window.matchMedia?.('(min-width: 40rem)').matches ?? true)

/** Окна решают, что делать, после всех входов и уходов этого кадра: порядок хуков между окнами любой */
export const afterThisFlush = () => Promise.resolve()
