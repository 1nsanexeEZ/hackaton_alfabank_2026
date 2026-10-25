<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'

import { LOGOUT_TIMING as T, registerLogoutPlayer, type LogoutPlan } from '../model/logout'

/**
 * Анимация выхода — «чёрная дыра», зеркало входа «сборка в знак»:
 * 1. сессия стирается сразу, экран плавно гаснет до чёрного, в центре проступает дыра с красным кольцом;
 * 2. буквы «А» — те же, что фон входа: красные и белые с объёмом и полупрозрачные — появляются со всех
 *    сторон, их немного и каждый раз разное число, и по прямой втягиваются в дыру, сжимаясь и затухая;
 * 3. дыра схлопывается в точку со вспышкой — под ней уже главная лендинга;
 * 4. главная раскрывается кругом из центра.
 *
 * Только transform, opacity и clip-path через Web Animations API. Клик или Esc — сразу главная.
 * При `prefers-reduced-motion` — без анимации: выход и переход.
 */

type Tone = 'red' | 'white' | 'ghost'

interface Glyph {
  key: number
  tone: Tone
  /** Откуда летит: смещение от центра экрана, px */
  x: number
  y: number
  rotate: number
  size: number
  delay: number
}

const GLYPH = 'А'
/** Сколько букв: каждый раз случайно в этих пределах — хаотично, но без перегруза */
const COUNT = { min: 7, max: 12 } as const
/** Красных и белых больше, полупрозрачных — для глубины */
const TONES: readonly Tone[] = ['red', 'red', 'white', 'white', 'ghost']

const running = ref(false)
const glyphs = shallowRef<Glyph[]>([])
const glyphEls = ref<HTMLElement[]>([])
const backdrop = ref<HTMLElement>()
const hole = ref<HTMLElement>()
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

/** Случайный набор букв по кругу экрана: угол с разбросом, разная дальность, кегль, тон и наклон */
function scatter(): Glyph[] {
  const count = COUNT.min + Math.floor(Math.random() * (COUNT.max - COUNT.min + 1))
  const radiusX = window.innerWidth * 0.44
  const radiusY = window.innerHeight * 0.43
  // На телефоне буквы мельче, на широком экране — как на входе
  const scale = Math.min(Math.max(window.innerWidth / 1280, 0.55), 1.2)
  return Array.from({ length: count }, (_, key) => {
    const sector = (Math.PI * 2) / count
    const angle = key * sector + (Math.random() - 0.5) * sector * 0.8
    const reach = 0.72 + Math.random() * 0.45
    return {
      key,
      tone: TONES[Math.floor(Math.random() * TONES.length)]!,
      x: Math.cos(angle) * radiusX * reach,
      y: Math.sin(angle) * radiusY * reach,
      rotate: Math.round((Math.random() - 0.5) * 50),
      size: Math.round((34 + Math.random() * Math.random() * 110) * scale),
      delay: Math.round(T.blackout * 0.6 + Math.random() * T.stagger),
    }
  })
}

function glyphStyle(glyph: Glyph): Record<string, string> {
  return { fontSize: `${glyph.size}px`, marginLeft: `${-glyph.size * 0.36}px`, marginTop: `${-glyph.size * 0.5}px` }
}

/** По прямой к центру: буква проступает на месте, разгоняется, сжимается в точку и гаснет у горизонта */
function suck(glyph: Glyph): Keyframe[] {
  return [
    { transform: `translate(${glyph.x.toFixed(0)}px, ${glyph.y.toFixed(0)}px) rotate(${glyph.rotate}deg) scale(1)`, opacity: 0 },
    { opacity: 1, offset: 0.14 },
    { opacity: 1, offset: 0.82 },
    { transform: 'translate(0px, 0px) rotate(0deg) scale(0.04)', opacity: 0 },
  ]
}

function hideShell(): void {
  shell = document.querySelector<HTMLElement>('[data-app-shell]')
  if (!shell) return
  void play(shell, [{ opacity: 1 }, { opacity: 0 }], { duration: T.blackout, easing: 'ease-in' })
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
  glyphs.value = []
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
  if (!document.querySelector('[data-app-shell]') || reducedMotion()) {
    plan.logout()
    await plan.navigate()
    return
  }
  const current = ++run
  glyphs.value = scatter()
  running.value = true
  document.addEventListener('keydown', onKeydown, true)
  await nextTick()

  // Сессии нет сразу: под погасшей страницей уже открывается главная
  hideShell()
  plan.logout()
  const navigation = plan.navigate().catch(() => undefined)

  void play(backdrop.value, [{ opacity: 0 }, { opacity: 1 }], { duration: T.blackout, easing: 'ease-in-out' })
  void play(hole.value, [{ transform: 'scale(0)' }, { transform: 'scale(1)' }], {
    duration: 240,
    delay: T.blackout * 0.5,
    easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  })

  const flights = glyphs.value.map((glyph, index) =>
    play(glyphEls.value[index], suck(glyph), { duration: T.suck, delay: glyph.delay, easing: 'cubic-bezier(0.55, 0, 0.9, 0.35)' }),
  )
  await Promise.all(flights)
  if (current !== run) return

  // Схлопывание: дыра в точку, вспышка с кольцом
  void play(hole.value, [{ transform: 'scale(1)' }, { transform: 'scale(0.06)' }], { duration: T.collapse, easing: 'cubic-bezier(0.7, 0, 0.9, 0.4)' })
  void play(flash.value, [{ opacity: 0, transform: 'scale(0.2)' }, { opacity: 1, transform: 'scale(1)', offset: 0.35 }, { opacity: 0, transform: 'scale(3.2)' }], {
    duration: T.collapse + 280,
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
  <div v-if="running" class="fixed inset-0 z-[140] cursor-default overflow-hidden select-none" aria-hidden="true" @click="cleanup">
    <div ref="backdrop" class="absolute inset-0 bg-[#050506]" />
    <div class="absolute top-1/2 left-1/2 size-0">
      <span
        v-for="glyph in glyphs"
        :key="glyph.key"
        ref="glyphEls"
        class="logout__glyph"
        :class="`is-${glyph.tone}`"
        :style="glyphStyle(glyph)"
        >{{ GLYPH }}</span
      >
      <span ref="hole" class="logout__hole" />
      <span ref="flash" class="logout__flash" />
    </div>
  </div>
</template>

<style scoped>
/* Те же буквы, что у фона входа (shared/ui/FloatingLetters): Inter 900, три тона, объём тенью */
.logout__glyph {
  position: absolute;
  top: 0;
  left: 0;
  font-weight: 900;
  line-height: 1;
  opacity: 0;
  will-change: transform, opacity;
}

.logout__glyph.is-red {
  color: var(--color-brand);
  text-shadow:
    0.01em 0.01em 0 #c42619,
    0.02em 0.02em 0 #b02217,
    0.03em 0.03em 0 #9c1e14,
    0.04em 0.04em 0 #881a11,
    0.05em 0.05em 0 #74160f,
    0.06em 0.06em 0 #60120c,
    0.08em 0.12em 0.16em rgb(0 0 0 / 0.5);
}

.logout__glyph.is-white {
  color: #fff;
  text-shadow:
    0.01em 0.01em 0 #dcdce2,
    0.02em 0.02em 0 #c8c8d0,
    0.03em 0.03em 0 #b4b4be,
    0.04em 0.04em 0 #a0a0ac,
    0.05em 0.05em 0 #8c8c9a,
    0.06em 0.06em 0 #787888,
    0.08em 0.12em 0.16em rgb(0 0 0 / 0.5);
}

.logout__glyph.is-ghost {
  color: rgb(255 255 255 / 0.18);
  text-shadow: 0.08em 0.12em 0.16em rgb(0 0 0 / 0.35);
}

/* Дыра: чёрная точка с красным кольцом, кольцо мягко дышит */
.logout__hole {
  position: absolute;
  width: 2.875rem;
  height: 2.875rem;
  margin: -1.4375rem 0 0 -1.4375rem;
  border-radius: 50%;
  background: radial-gradient(circle, #000 60%, #120404 100%);
  transform: scale(0);
  animation: logout-pulse 1.2s ease-in-out infinite;
}

.logout__flash {
  position: absolute;
  width: 6.25rem;
  height: 6.25rem;
  margin: -3.125rem 0 0 -3.125rem;
  border-radius: 50%;
  opacity: 0;
  background: radial-gradient(circle, #fff 0 7%, rgb(255 255 255 / 0.55) 14%, rgb(239 49 36 / 0.35) 42%, transparent 70%);
  box-shadow: 0 0 0 2px rgb(239 49 36 / 0.8);
}

@keyframes logout-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 2px rgb(239 49 36 / 0.85),
      0 0 1.75rem 0.375rem rgb(239 49 36 / 0.35);
  }
  50% {
    box-shadow:
      0 0 0 2px rgb(239 49 36 / 1),
      0 0 2.75rem 0.75rem rgb(239 49 36 / 0.5);
  }
}
</style>
