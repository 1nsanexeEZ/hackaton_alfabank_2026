/** Что нужно анимации выхода от страницы: стереть сессию и уйти на главную */
export interface LogoutPlan {
  /** Стирает сессию — вызывается сразу, до анимации: даже прерванная, она кабинет уже закрыла */
  logout: () => void
  /** Переход на главную лендинга; раскрытие ждёт, пока она отрисуется */
  navigate: () => Promise<unknown>
}

type Player = (plan: LogoutPlan) => void

let player: Player | null = null

/** Анимацию держит один компонент в App.vue — он и регистрируется здесь */
export function registerLogoutPlayer(next: Player | null): void {
  player = next
}

/** Выйти с анимацией «чёрной дыры»; компонента нет (тесты, другая сборка) — просто выйти и уйти на главную */
export function signOutWithTransition(plan: LogoutPlan): void {
  if (player) {
    player(plan)
    return
  }
  plan.logout()
  void plan.navigate()
}

/**
 * Тайминг «чёрной дыры», мс: около 1,8 с от нажатия до главной.
 * Экран гаснет, буквы «А» втягиваются, дыра схлопывается во вспышку, главная раскрывается кругом из центра.
 */
export const LOGOUT_TIMING = {
  /** Страница плавно гаснет до чёрного, в центре проступает дыра */
  blackout: 280,
  /** Полёт буквы по прямой в дыру */
  suck: 850,
  /** Разброс старта букв: прилетают не строем */
  stagger: 220,
  /** Дыра сжимается в точку, вспышка */
  collapse: 240,
  /** Главная раскрывается кругом из центра */
  reveal: 500,
} as const
