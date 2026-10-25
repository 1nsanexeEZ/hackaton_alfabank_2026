<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef } from 'vue'

import type { LetterSnapshot } from '@/shared/ui'

import { contourPoint, signLayout, signPath, type SignLayout } from '../model/sign'
import { TIMING, type DrawerExit, type LoginTransitionPlan } from '../model/transition'

/**
 * Анимация после успешного входа — «сборка в знак»:
 * 1. галочка на кнопке (её рисует панель), панель уходит;
 * 2. буквы фона подменяются своими копиями и долетают до точек на штрихах «А», знак «впечатывается»;
 * 3a. вход на профиль: знак заливает экран красным, под ним открывается /profile; профиль раскрывается кругом
 *     из центра, белая «А» улетает в логотип шапки;
 * 3b. вход перед заявкой: знак сам улетает в логотип, затем открывается мастер заявки;
 * 4. логотип подсвечивается — «долетела»: вспышка, кольцо и свечение около секунды, страница уже доступна.
 *
 * Только transform, opacity и clip-path, всё — Web Animations API: стили страницы с паузой анимаций под
 * модалкой и сокращением анимаций при reduced motion её не задевают. Клик или Esc — сразу финал.
 * При `prefers-reduced-motion` — без полёта: сразу нужный экран и проявление 200 мс.
 */

const GLYPH = 'А'

interface Clone {
  key: number
  style: Record<string, string>
}

interface Box {
  left: number
  top: number
  width: number
  height: number
}

const running = ref(false)
const coverShown = ref(false)
const markShown = ref(false)
const skippable = ref(false)
const layout = shallowRef<SignLayout | null>(null)
const clones = shallowRef<Clone[]>([])
const glowBox = shallowRef<Box | null>(null)

const cloneEls = ref<HTMLElement[]>([])
const sign = ref<SVGSVGElement>()
const mark = ref<SVGSVGElement>()
const halo = ref<HTMLElement>()
const ring = ref<HTMLElement>()
const flash = ref<HTMLElement>()

const signD = computed(() => (layout.value ? signPath(layout.value) : ''))
const markD = computed(() => (layout.value ? signPath(layout.value, layout.value.height * 0.82) : ''))
const glowStyle = computed(() => {
  const box = glowBox.value
  return box ? { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` } : {}
})

let plan: LoginTransitionPlan | null = null
/** Номер текущего прогона: пропуск и новый вход его меняют, и отложенные шаги старого прогона молча выходят */
let run = 0
/** Слои анимации — гасятся вместе с ней; хвост (подсветка, появление карточек) доигрывает сам */
let layerAnimations: Animation[] = []
let tailAnimations: Animation[] = []
let shell: HTMLElement | null = null
let closed = false
let navigation: Promise<unknown> | null = null
let finished = false

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))
const frame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

/** Новая страница отрисована: Vue обновил DOM и браузер успел нарисовать два кадра */
async function painted(): Promise<void> {
  await nextTick()
  await frame()
  await frame()
}

function play(target: Element | null | undefined, keyframes: Keyframe[], options: KeyframeAnimationOptions, tail = false): Promise<void> {
  if (!target) return Promise.resolve()
  const animation = target.animate(keyframes, { fill: 'both', ...options })
  ;(tail ? tailAnimations : layerAnimations).push(animation)
  return animation.finished.then(
    () => undefined,
    () => undefined,
  )
}

function cancel(list: Animation[]): void {
  for (const animation of list) animation.cancel()
  list.length = 0
}

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Логотип в шапке — туда летит «А» */
const brandLogo = () => document.querySelector<SVGElement>('header [data-brand-logo] svg')

function center(element: Element): { x: number; y: number; height: number } {
  const box = element.getBoundingClientRect()
  return { x: box.left + box.width / 2, y: box.top + box.height / 2, height: box.height }
}

function closeDrawer(exit: DrawerExit): void {
  if (closed || !plan) return
  closed = true
  plan.close(exit)
}

function startNavigation(): Promise<unknown> {
  if (!navigation && plan) navigation = plan.navigate().catch(() => undefined)
  return navigation ?? Promise.resolve()
}

function focusHeading(): void {
  document.querySelector<HTMLElement>('main h1')?.focus({ preventScroll: true })
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.preventDefault()
  skip()
}

/** Страница поверх красной заливки и открывается кругом из центра */
function raiseShell(view: SignLayout): void {
  shell = document.querySelector<HTMLElement>('[data-app-shell]')
  if (!shell) return
  shell.style.position = 'relative'
  shell.style.zIndex = '130'
  const at = `at ${view.center.x}px ${view.center.y + window.scrollY}px`
  void play(shell, [{ clipPath: `circle(0px ${at})` }, { clipPath: `circle(${Math.round(view.reveal)}px ${at})` }], {
    duration: TIMING.open,
    easing: 'cubic-bezier(0.7, 0, 0.2, 1)',
  })
}

function restoreShell(): void {
  if (!shell) return
  shell.style.position = ''
  shell.style.zIndex = ''
  shell = null
}

/** Карточки профиля поднимаются лесенкой — те, что страница пометила `data-rise` */
function riseProfile(): void {
  document.querySelectorAll<HTMLElement>('main [data-rise]').forEach((element, index) => {
    void play(
      element,
      [
        { transform: 'translateY(12px)', opacity: 0 },
        { transform: 'translateY(0px)', opacity: 1 },
      ],
      { duration: 340, delay: 180 + index * 30, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', fill: 'backwards' },
      true,
    )
  })
}

/** Буквы фона — своими копиями на тех же местах, в тот же кадр, когда панель гасит свои */
function takeLetters(letters: LetterSnapshot[]): void {
  clones.value = letters.map((letter, key) => ({
    key,
    style: {
      left: `${letter.x}px`,
      top: `${letter.y}px`,
      fontSize: `${letter.size}px`,
      color: letter.color,
      textShadow: letter.shadow,
      filter: letter.filter,
      opacity: String(letter.opacity),
      transform: `translate(-50%, -50%) rotate(${letter.rotate}deg)`,
    },
  }))
}

/** Каждая буква долетает до своей точки на штрихах знака и гаснет только там; затем знак «впечатывается» */
function gather(letters: LetterSnapshot[], view: SignLayout): void {
  const landed = view.height * 0.18
  for (const element of cloneEls.value) {
    const index = Number(element.dataset.index)
    const letter = letters[index]
    if (!letter) continue
    const point = contourPoint(view, index)
    const delay = index * 9
    const scale = Math.min(1, landed / letter.size)
    void play(
      element,
      [
        { transform: `translate(-50%, -50%) translate(0px, 0px) scale(1) rotate(${letter.rotate}deg)` },
        {
          transform: `translate(-50%, -50%) translate(${Math.round(point.x - letter.x)}px, ${Math.round(point.y - letter.y)}px) scale(${scale.toFixed(3)}) rotate(0deg)`,
        },
      ],
      { duration: 340, delay, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' },
    )
    void play(element, [{ opacity: letter.opacity }, { opacity: 0 }], { duration: 90, delay: delay + 300, easing: 'ease' })
  }
  void play(sign.value, [{ transform: 'scale(0.85)' }, { transform: 'scale(1)' }], {
    duration: 220,
    delay: 400,
    easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  })
  void play(sign.value, [{ opacity: 0 }, { opacity: 1 }], { duration: 120, delay: 400, easing: 'ease' })
}

/** «Долетела»: логотип пружинит, вспышка, кольцо расходится, свечение держится и гаснет */
async function glowLogo(logo: Element | null, soft = false): Promise<void> {
  if (!logo) return
  const box = logo.getBoundingClientRect()
  glowBox.value = { left: box.left, top: box.top, width: box.width, height: box.height }
  await nextTick()
  if (!soft) {
    void play(logo, [{ transform: 'scale(1.14)' }, { transform: 'scale(1)' }], {
      duration: 480,
      easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      fill: 'none',
    }, true)
    void play(flash.value, [{ opacity: 0.55 }, { opacity: 0 }], { duration: 320, easing: 'ease' }, true)
    void play(
      ring.value,
      [
        { transform: 'scale(1)', opacity: 0.9 },
        { transform: 'scale(2.6)', opacity: 0 },
      ],
      { duration: 700, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' },
      true,
    )
  }
  const current = run
  await play(
    halo.value,
    [{ opacity: soft ? 0 : 0.35 }, { opacity: 1, offset: 0.17 }, { opacity: 1, offset: 0.5 }, { opacity: 0 }],
    { duration: soft ? 1000 : TIMING.glow, easing: 'ease' },
    true,
  )
  if (current === run) glowBox.value = null
}

/** Слои анимации убираются; вход завершён — страница своя */
function complete(): void {
  cancel(layerAnimations)
  restoreShell()
  running.value = false
  coverShown.value = false
  markShown.value = false
  skippable.value = false
  clones.value = []
  document.removeEventListener('keydown', onKeydown)
  if (!finished && plan) {
    finished = true
    plan.done()
  }
}

async function toProfile(current: number, view: SignLayout, letters: LetterSnapshot[]): Promise<void> {
  const alive = () => current === run
  gather(letters, view)
  await sleep(TIMING.cover)
  if (!alive()) return
  coverShown.value = true
  const routed = startNavigation()
  await sleep(TIMING.gather - TIMING.cover)
  if (!alive()) return

  // Знак заливает экран, на красном проявляется белая «А»
  markShown.value = true
  await nextTick()
  void play(sign.value, [{ transform: 'scale(1)' }, { transform: `scale(${view.flood.toFixed(2)})` }], {
    duration: TIMING.flood,
    easing: 'cubic-bezier(0.7, 0, 0.84, 0)',
  })
  void play(
    mark.value,
    [
      { transform: 'translate(0px, 0px) scale(0.85)', opacity: 0 },
      { transform: 'translate(0px, 0px) scale(1)', opacity: 1 },
    ],
    { duration: 240, delay: 170, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' },
  )
  await Promise.all([sleep(TIMING.flood), routed.then(painted)])
  if (!alive()) return

  // Профиль раскрывается из центра, белая «А» летит в логотип шапки
  clones.value = []
  raiseShell(view)
  riseProfile()
  const logo = brandLogo()
  if (logo) {
    const target = center(logo)
    const scale = (target.height * 0.55) / (view.height * 0.82)
    void play(
      mark.value,
      [
        { transform: 'translate(0px, 0px) scale(1)' },
        { transform: `translate(${Math.round(target.x - view.center.x)}px, ${Math.round(target.y - view.center.y)}px) scale(${scale.toFixed(3)})` },
      ],
      { duration: TIMING.open, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' },
    )
    void play(mark.value, [{ opacity: 1 }, { opacity: 0 }], { duration: 80, delay: TIMING.open - 80 })
  }
  await sleep(TIMING.open)
  if (!alive()) return

  complete()
  void glowLogo(logo)
  focusHeading()
}

async function toApplication(current: number, view: SignLayout, letters: LetterSnapshot[]): Promise<void> {
  const alive = () => current === run
  gather(letters, view)
  await sleep(TIMING.gather)
  if (!alive()) return

  // Знак улетает в логотип и сливается с ним; размытие к этому времени уже погасло
  const logo = brandLogo()
  if (logo) {
    const target = center(logo)
    const scale = (target.height * 0.55) / view.height
    const dx = target.x - view.center.x
    const dy = target.y - view.pivot.y - scale * (view.center.y - view.pivot.y)
    void play(sign.value, [{ transform: 'translate(0px, 0px) scale(1)' }, { transform: `translate(${Math.round(dx)}px, ${Math.round(dy)}px) scale(${scale.toFixed(3)})` }], {
      duration: TIMING.fly,
      easing: 'cubic-bezier(0.65, 0, 0.35, 1)',
    })
    void play(sign.value, [{ opacity: 1 }, { opacity: 0 }], { duration: 80, delay: TIMING.fly - 80 })
  }
  await sleep(TIMING.fly)
  if (!alive()) return

  cancel(layerAnimations)
  running.value = false
  clones.value = []
  void glowLogo(logo)
  await sleep(TIMING.wizardDelay)
  if (!alive()) return
  complete()
}

/** Без движения: сразу нужный экран, страница проявляется за 200 мс, логотип мягко светится */
async function calm(current: number): Promise<void> {
  await sleep(TIMING.confirm)
  if (current !== run || !plan) return
  if (plan.next === 'profile') {
    await startNavigation()
    await painted()
    if (current !== run) return
    closeDrawer('close')
    void play(document.querySelector('main'), [{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: 'ease', fill: 'backwards' }, true)
    void glowLogo(brandLogo(), true)
  } else {
    closeDrawer('close')
  }
  complete()
  if (plan.next === 'profile') focusHeading()
}

/**
 * Запустить анимацию входа. Панель уже показала галочку; дальше анимация сама закрывает её,
 * при входе на профиль меняет маршрут и в конце сообщает, что вход завершён.
 */
async function start(next: LoginTransitionPlan): Promise<void> {
  skip()
  cancel(tailAnimations)
  glowBox.value = null
  plan = next
  const current = ++run
  closed = false
  navigation = null
  finished = false
  skippable.value = true
  document.addEventListener('keydown', onKeydown)

  if (reducedMotion()) return calm(current)

  const view = signLayout(window.innerWidth, window.innerHeight)
  layout.value = view
  running.value = true
  await sleep(TIMING.confirm)
  if (current !== run) return

  const letters = next.letters()
  takeLetters(letters)
  closeDrawer(next.next === 'profile' ? 'handoff-dark' : 'handoff')
  await nextTick()
  if (current !== run) return
  await (next.next === 'profile' ? toProfile(current, view, letters) : toApplication(current, view, letters))
}

/** Клик или Esc во время анимации: сразу финал — панель закрыта, нужный экран открыт, слоёв поверх нет */
function skip(): void {
  if (!plan || finished) return
  run += 1
  cancel(layerAnimations)
  cancel(tailAnimations)
  glowBox.value = null
  closeDrawer('close')
  if (plan.next === 'profile') void startNavigation().then(painted).then(focusHeading)
  complete()
}

onBeforeUnmount(() => {
  run += 1
  cancel(layerAnimations)
  cancel(tailAnimations)
  restoreShell()
  document.removeEventListener('keydown', onKeydown)
})

defineExpose({ start })
</script>

<template>
  <Teleport to="body">
    <div v-if="running" class="pointer-events-none fixed inset-0 z-[120] overflow-hidden" aria-hidden="true">
      <div v-if="coverShown" class="absolute inset-0 bg-night" />
      <span v-for="clone in clones" :key="clone.key" ref="cloneEls" :data-index="clone.key" class="login-clone" :style="clone.style">{{ GLYPH }}</span>
      <svg
        v-if="layout"
        ref="sign"
        class="absolute inset-0 size-full overflow-visible opacity-0"
        :style="{ transformOrigin: `${layout.pivot.x}px ${layout.pivot.y}px` }"
      >
        <path :d="signD" class="fill-brand" fill-rule="evenodd" />
      </svg>
    </div>
    <svg
      v-if="markShown && layout"
      ref="mark"
      class="pointer-events-none fixed inset-0 z-[140] size-full overflow-visible opacity-0"
      :style="{ transformOrigin: `${layout.center.x}px ${layout.center.y}px` }"
      aria-hidden="true"
    >
      <path :d="markD" fill="#fff" fill-rule="evenodd" />
    </svg>
    <div v-if="glowBox" class="pointer-events-none fixed z-[99]" :style="glowStyle" aria-hidden="true">
      <span ref="halo" class="login-glow login-glow--halo" />
      <span ref="ring" class="login-glow login-glow--ring" />
      <span ref="flash" class="login-glow login-glow--flash" />
    </div>
    <button
      v-if="skippable"
      type="button"
      class="fixed inset-0 z-[150] cursor-default"
      aria-label="Пропустить анимацию"
      @click="skip"
    />
  </Teleport>
</template>

<style scoped>
.login-clone {
  position: absolute;
  display: block;
  font-weight: 900;
  line-height: 1;
  white-space: nowrap;
  will-change: transform, opacity;
}

.login-glow {
  position: absolute;
  inset: 0;
  border-radius: 25%;
  opacity: 0;
}

/* Свечение — только снаружи логотипа, сам знак им не закрашивается */
.login-glow--halo {
  box-shadow:
    0 0 1.5rem 0.5rem rgb(239 49 36 / 0.65),
    0 0 0.5rem 0.125rem rgb(239 49 36 / 0.8);
}

.login-glow--ring {
  box-shadow: 0 0 0 2px var(--color-brand);
}

.login-glow--flash {
  background: #fff;
}
</style>
