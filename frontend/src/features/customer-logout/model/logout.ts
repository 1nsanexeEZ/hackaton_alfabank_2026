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
 * Тайминг «чёрной дыры», мс: около 1,4 с от нажатия до главной.
 * Буквы втягиваются, дыра схлопывается во вспышку, главная раскрывается кругом из центра.
 */
export const LOGOUT_TIMING = {
  /** Карточки и фон страницы гаснут, остаются только буквы */
  fade: 260,
  /** Буквы летят по спирали в центр; дальние стартуют позже */
  suck: 760,
  /** Разброс старта букв по дальности */
  stagger: 180,
  /** Дыра сжимается в точку, вспышка */
  collapse: 220,
  /** Главная раскрывается кругом из центра */
  reveal: 460,
} as const
