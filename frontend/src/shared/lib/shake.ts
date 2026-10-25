/**
 * Не заполнили обязательное или не выбрали нужное — поле или кнопка вздрагивает и вспыхивает красным
 * (класс `is-invalid-shake`, анимация — в app/styles). Повторная попытка трясёт снова: класс снимается
 * и ставится заново. При prefers-reduced-motion остаётся только красная вспышка без движения.
 */
const SHAKE_CLASS = 'is-invalid-shake'

export function shakeInvalid(elements: Iterable<Element | null | undefined>): void {
  for (const element of elements) {
    if (!element) continue
    element.classList.remove(SHAKE_CLASS)
    // Перезапуск анимации: браузер должен увидеть элемент без класса
    void (element as HTMLElement).offsetWidth
    element.classList.add(SHAKE_CLASS)
    element.addEventListener('animationend', () => element.classList.remove(SHAKE_CLASS), { once: true })
  }
}

/**
 * Что трясти внутри формы: поля, которые валидация пометила `aria-invalid="true"`, и свои группы выбора
 * с `data-invalid`. У чекбокса трясётся вся строка с подписью, у поля ввода — само поле.
 */
export function shakeInvalidIn(root: ParentNode | null | undefined): void {
  if (!root) return
  const marked = [...root.querySelectorAll<HTMLElement>('[aria-invalid="true"], [data-invalid="true"]')]
  shakeInvalid(marked.map((element) => (element instanceof HTMLInputElement && element.type === 'checkbox' ? element.closest('label') : element)))
}

/**
 * Для всех форм сразу: после отправки формы, когда валидация уже отрисовала ошибки, трясём помеченные поля.
 * Формы с ошибкой не уходят на сервер — их отправку обрабатывает сам компонент; мы только смотрим на результат.
 */
export function shakeInvalidOnSubmit(): () => void {
  const onSubmit = (event: Event) => {
    const form = event.target
    if (!(form instanceof HTMLFormElement)) return
    // setTimeout, а не nextTick: ждём, пока Vue перерисует ошибки после обработчика отправки
    window.setTimeout(() => shakeInvalidIn(form), 0)
  }
  document.addEventListener('submit', onSubmit, true)
  return () => document.removeEventListener('submit', onSubmit, true)
}
