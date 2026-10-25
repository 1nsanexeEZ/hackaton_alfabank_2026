<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'

import { LOGOUT_TIMING as T, registerLogoutPlayer, type LogoutPlan } from '../model/logout'

/**
 * Анимация выхода — «чёрная дыра», зеркало входа «сборка в знак»:
 * 1. берём снимок букв на экране и подменяем их своими копиями, сессия стирается сразу;
 * 2. страница гаснет, копии букв по спирали втягиваются в дыру в центре, светлея, сжимаясь и затухая;
 * 3. дыра схлопывается в точку со вспышкой — под ней уже главная лендинга;
 * 4. главная раскрывается кругом из центра.
 *
 * Только transform, opacity, color и clip-path через Web Animations API. Клик или Esc — сразу главная.
 * При `prefers-reduced-motion` — без полёта: выход и переход.
 */

interface Letter {
  key: number
  char: string
  style: Record<string, string>
  /** Смещение от центра экрана — для спирали */
  dx: number
  dy: number
}

const MAX_LETTERS = 220

const running = ref(false)
const letters = shallowRef<Letter[]>([])
const letterEls = ref<HTMLElement[]>([])
const backdrop = ref<HTMLElement>()
const hole = ref<HTMLElement>()
const disk = ref<HTMLElement>()
const flash = ref<HTMLElement>()

let animations: Animation[] = []
let shell: HTMLElement | null = null
let run = 0

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))
const frame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function play(target: Element | null | undefined, keyframes: Keyframe[], options: KeyframeAnimationOptions): Promise<void> {
  if (!target) return Promise.resolve()
  const animation = target.animate(keyframes, { fill: 'both', ...options })
  animations.push(animation)
  return animation.finished.then(
    () => undefined,
    () => undefined,
  )
}

/** Буквы видимого текста страницы: позиция каждой и её шрифт; длинный текст — равномерной выборкой */
function snapshot(root: Element): Letter[] {
  const width = window.innerWidth
  const height = window.innerHeight
  const cx = width / 2
  const cy = height / 2
  const found: Omit<Letter, 'key'>[] = []
  const range = document.createRange()
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => (node.nodeValue?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  })
  for (let node = walker.nextNode(); node && found.length < 2400; node = walker.nextNode()) {
    const parent = node.parentElement
    if (!parent) continue
    const css = getComputedStyle(parent)
    if (css.visibility === 'hidden' || Number(css.opacity) === 0) continue
    const text = node.nodeValue ?? ''
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index]!
      if (/\s/.test(char)) continue
      range.setStart(node, index)
      range.setEnd(node, index + 1)
      const box = range.getBoundingClientRect()
      if (!box.width || box.bottom < 0 || box.top > height || box.right < 0 || box.left > width) continue
      found.push({
        char,
        dx: box.left + box.width / 2 - cx,
        dy: box.top + box.height / 2 - cy,
        style: {
          left: `${box.left}px`,
          top: `${box.top}px`,
          fontSize: css.fontSize,
          fontWeight: css.fontWeight,
          fontFamily: css.fontFamily,
          lineHeight: `${box.height}px`,
          color: css.color,
        },
      })
    }
  }
  const step = Math.max(found.length / MAX_LETTERS, 1)
  const picked = found.length > MAX_LETTERS ? Array.from({ length: MAX_LETTERS }, (_, k) => found[Math.floor(k * step)]!) : found
  return picked.map((letter, key) => ({ ...letter, key }))
}

/** Путь буквы к центру: спираль с сужением, буква светлеет, вращается, сжимается и гаснет у горизонта */
function spiral(letter: Letter, turn: number): Keyframe[] {
  const radius = Math.hypot(letter.dx, letter.dy)
  const start = Math.atan2(letter.dy, letter.dx)
  const steps = 8
  return Array.from({ length: steps + 1 }, (_, k) => {
    const t = k / steps
    const r = radius * (1 - t) ** 1.7
    const angle = start + turn * t
    const x = r * Math.cos(angle) - letter.dx
    const y = r * Math.sin(angle) - letter.dy
    const scale = 1 - 0.92 * t ** 1.3
    return {
      offset: t,
      transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${((turn * t * 180) / Math.PI).toFixed(0)}deg) scale(${scale.toFixed(3)})`,
      opacity: t < 0.78 ? 1 : Math.max(1 - (t - 0.78) / 0.22, 0),
      color: t < 0.25 ? letter.style.color! : 'rgba(255, 255, 255, 0.92)',
    }
  })
}

function hideShell(): void {
  shell = document.querySelector<HTMLElement>('[data-app-shell]')
  if (!shell) return
  void play(shell, [{ opacity: 1 }, { opacity: 0 }], { duration: T.fade, easing: 'ease-out' })
}

/** Главная поверх дыры и раскрывается кругом из центра */
function revealShell(): Promise<void> {
  if (!shell) return Promise.resolve()
  shell.style.position = 'relative'
  shell.style.zIndex = '150'
  const at = `at ${window.innerWidth / 2}px ${window.innerHeight / 2 + window.scrollY}px`
  const radius = Math.hypot(window.innerWidth, window.innerHeight)
  return play(shell, [{ opacity: 1, clipPath: `circle(0px ${at})` }, { opacity: 1, clipPath: `circle(${Math.round(radius)}px ${at})` }], {
    duration: T.reveal,
    easing: 'cubic-bezier(0.7, 0, 0.2, 1)',
  })
}

function cleanup(): void {
  // Отложенные шаги прерванного прогона молча выходят
  run += 1
  for (const animation of animations) animation.cancel()
  animations = []
  if (shell) {
    shell.style.position = ''
    shell.style.zIndex = ''
  }
  shell = null
  letters.value = []
  running.value = false
  document.removeEventListener('keydown', onKeydown, true)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.preventDefault()
  cleanup()
}

async function start(plan: LogoutPlan): Promise<void> {
  if (running.value) return
  const root = document.querySelector('[data-app-shell]')
  if (!root || reducedMotion()) {
    plan.logout()
    await plan.navigate()
    return
  }
  const current = ++run
  letters.value = snapshot(root)
  running.value = true
  document.addEventListener('keydown', onKeydown, true)
  await nextTick()

  // Сессии нет сразу: под погасшей страницей уже открывается главная
  hideShell()
  plan.logout()
  const navigation = plan.navigate().catch(() => undefined)

  void play(backdrop.value, [{ opacity: 0 }, { opacity: 1 }], { duration: T.fade, easing: 'ease-out' })
  void play(hole.value, [{ transform: 'scale(0)' }, { transform: 'scale(1)' }], { duration: T.fade + 120, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' })
  void play(disk.value, [{ transform: 'rotate(0deg)' }, { transform: 'rotate(540deg)' }], { duration: T.fade + T.suck + T.stagger, easing: 'cubic-bezier(0.4, 0, 0.6, 1)' })

  const turn = Math.PI * 1.6
  const farthest = Math.max(...letters.value.map((letter) => Math.hypot(letter.dx, letter.dy)), 1)
  const flights = letters.value.map((letter, index) =>
    play(letterEls.value[index], spiral(letter, turn), {
      duration: T.suck,
      delay: 80 + (Math.hypot(letter.dx, letter.dy) / farthest) * T.stagger,
      easing: 'cubic-bezier(0.55, 0, 0.85, 0.3)',
    }),
  )
  await Promise.all(flights)
  if (current !== run) return

  // Схлопывание: дыра в точку, вспышка, кольцо расходится
  void play(hole.value, [{ transform: 'scale(1)' }, { transform: 'scale(0.08)' }], { duration: T.collapse, easing: 'cubic-bezier(0.7, 0, 0.9, 0.4)' })
  void play(flash.value, [{ opacity: 0, transform: 'scale(0.2)' }, { opacity: 1, transform: 'scale(1)', offset: 0.35 }, { opacity: 0, transform: 'scale(2.6)' }], {
    duration: T.collapse + 260,
    easing: 'ease-out',
  })
  await Promise.all([navigation, sleep(T.collapse)])
  await frame()
  await frame()
  if (current !== run) return

  await revealShell()
  if (current !== run) return
  await play(backdrop.value, [{ opacity: 1 }, { opacity: 0 }], { duration: 160 })
  cleanup()
}

onMounted(() => registerLogoutPlayer((plan) => void start(plan)))
onBeforeUnmount(() => {
  registerLogoutPlayer(null)
  cleanup()
})
</script>

<template>
  <div v-if="running" class="fixed inset-0 z-[140] cursor-default select-none" aria-hidden="true" @click="cleanup">
    <div ref="backdrop" class="absolute inset-0 bg-[#050506]" />
    <span
      v-for="letter in letters"
      :key="letter.key"
      ref="letterEls"
      class="absolute whitespace-pre will-change-transform"
      :style="letter.style"
      >{{ letter.char }}</span
    >
    <div class="pointer-events-none absolute top-1/2 left-1/2 size-0">
      <div ref="hole" class="logout__hole">
        <span ref="disk" class="logout__disk" />
        <span class="logout__core" />
      </div>
      <span ref="flash" class="logout__flash" />
    </div>
  </div>
</template>

<style scoped>
.logout__hole {
  position: absolute;
  width: 15rem;
  height: 15rem;
  margin: -7.5rem 0 0 -7.5rem;
}

/* Диск аккреции в фирменном красном */
.logout__disk {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, rgb(239 49 36 / 0), rgb(239 49 36 / 0.7), rgb(255 170 120 / 0.45), rgb(239 49 36 / 0) 62%);
  opacity: 0.85;
}

.logout__core {
  position: absolute;
  inset: 32%;
  border-radius: 50%;
  background: radial-gradient(circle, #000 58%, rgb(0 0 0 / 0.85) 66%, rgb(239 49 36 / 0) 76%);
  box-shadow: 0 0 3rem 0.5rem rgb(239 49 36 / 0.4);
}

.logout__flash {
  position: absolute;
  width: 8rem;
  height: 8rem;
  margin: -4rem 0 0 -4rem;
  border-radius: 50%;
  opacity: 0;
  background: radial-gradient(circle, #fff 0 6%, rgb(255 255 255 / 0.6) 12%, rgb(239 49 36 / 0.35) 40%, transparent 70%);
  box-shadow: 0 0 0 2px rgb(239 49 36 / 0.8);
}
</style>
