<script setup lang="ts">
/**
 * Декоративный слой из букв «А» разного размера: влетают и хаотично плавают, у каждой свой путь,
 * наклон и период, поэтому движение не повторяется. На широком экране — в 3D (перспектива,
 * глубина, объём тенью), на узком — плоско, чтобы не нагружать телефон. Дальние буквы мельче,
 * прозрачнее и размыты. Размеры в единицах контейнера (cqmin): слой подстраивается под свою
 * область — левую часть экрана на десктопе или полосу над панелью на телефоне.
 * Положения детерминированы: картинка одна и та же при каждом открытии.
 * Когда предок помечен `data-leaving` (так BaseDrawer помечает фон при закрытии), буквы улетают
 * обратно в глубину (3D) или схлопываются (плоско).
 * `snapshot()` отдаёт, где и какими буквы видны сейчас: по нему анимация входа подменяет их своими копиями.
 */
import { ref } from 'vue'

import type { LetterSnapshot } from './letters'

withDefaults(defineProps<{ glyph?: string }>(), { glyph: 'А' })

/** Перспектива сцены, px — та же, что в стилях `.letters` */
const PERSPECTIVE = 1000

type Tone = 'red' | 'white' | 'ghost'

interface Spot {
  /** Левый верхний угол, % контейнера */
  x: number
  y: number
  /** Кегль, cqmin */
  size: number
  tone: Tone
  opacity: number
  /** Размытие, px: дальний план */
  blur: number
  /** Глубина в 3D, px: ближе — больше */
  depth: number
}

/** Псевдослучайное число 0…1, одно и то же для пары (i, k) */
function rand(i: number, k: number): number {
  const x = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453
  return x - Math.floor(x)
}

// Крупные буквы расставлены вручную, чтобы держалась композиция; мелкие дальние — россыпью
const SPOTS: Spot[] = [
  { x: 6, y: 6, size: 32, tone: 'red', opacity: 1, blur: 0, depth: 140 },
  { x: 44, y: 34, size: 28, tone: 'ghost', opacity: 1, blur: 0, depth: 80 },
  { x: 12, y: 54, size: 24, tone: 'red', opacity: 1, blur: 0, depth: 100 },
  { x: 60, y: 6, size: 17, tone: 'white', opacity: 0.9, blur: 0, depth: 0 },
  { x: 34, y: 10, size: 12, tone: 'red', opacity: 0.85, blur: 0, depth: -40 },
  { x: 66, y: 64, size: 19, tone: 'white', opacity: 0.9, blur: 0, depth: 20 },
  { x: 2, y: 34, size: 13, tone: 'ghost', opacity: 0.8, blur: 0, depth: -60 },
  { x: 40, y: 72, size: 14, tone: 'red', opacity: 0.85, blur: 0, depth: -20 },
  ...Array.from({ length: 8 }, (_, k): Spot => ({
    x: Math.round(4 + rand(k, 7) * 76),
    y: Math.round(4 + rand(k, 8) * 78),
    size: Math.round((4 + rand(k, 9) * 5.5) * 10) / 10,
    tone: k % 2 ? 'white' : 'ghost',
    opacity: Math.round((0.3 + rand(k, 10) * 0.3) * 100) / 100,
    blur: 1 + Math.round(rand(k, 11) * 2),
    depth: -300,
  })),
]

const letters = SPOTS.map((spot, i) => {
  const r = (k: number) => rand(i + 20, k)
  const period = Math.round((7 + r(12) * 8) * 10) / 10
  return {
    key: i,
    tone: spot.tone,
    driftStyle: {
      left: `${spot.x}%`,
      top: `${spot.y}%`,
      opacity: String(spot.opacity),
      filter: spot.blur ? `blur(${spot.blur}px)` : undefined,
      '--dx': (1.5 + r(13) * 3).toFixed(2),
      '--dy': (1.3 + r(14) * 2.7).toFixed(2),
      '--rot': `${Math.round(4 + r(15) * 10)}deg`,
      '--spin': `${Math.round(10 + r(16) * 25)}deg`,
      '--period': `${period}s`,
      '--phase': `-${Math.round(r(17) * period * 10) / 10}s`,
    },
    glyphStyle: {
      '--size': String(spot.size),
      '--delay': `${150 + i * 60}ms`,
      '--from-x': ((r(1) - 0.5) * 140).toFixed(1),
      '--from-y': ((r(2) - 0.5) * 100).toFixed(1),
      '--from-rx': `${Math.round((r(3) - 0.5) * 360)}deg`,
      '--from-ry': `${Math.round((r(4) - 0.5) * 360)}deg`,
      '--from-turn': `${Math.round((r(7) - 0.5) * 180)}deg`,
      '--depth': `${spot.depth}px`,
      '--yaw': `${Math.round((r(5) - 0.5) * 50)}deg`,
      '--tilt': `${Math.round((r(6) - 0.5) * 30)}deg`,
      '--exit-delay': `${Math.round(r(18) * 120)}ms`,
    },
  }
})

const glyphs = ref<HTMLElement[]>([])

/**
 * Где и какими буквы видны в эту секунду. Размер — видимый: на широком экране буква ближе или дальше
 * по глубине и кажется крупнее или мельче своего кегля (поправка — по перспективе сцены).
 */
function snapshot(): LetterSnapshot[] {
  const deep = window.matchMedia('(width >= 64rem)').matches
  return glyphs.value.map((el) => {
    const rect = el.getBoundingClientRect()
    const own = getComputedStyle(el)
    const drift = el.parentElement ? getComputedStyle(el.parentElement) : null
    const depth = deep ? Number.parseFloat(own.getPropertyValue('--depth')) || 0 : 0
    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      size: Number.parseFloat(own.fontSize) * (PERSPECTIVE / (PERSPECTIVE - depth)),
      rotate: Number.parseFloat(own.getPropertyValue('--tilt')) || 0,
      color: own.color,
      shadow: own.textShadow,
      opacity: Number(own.opacity) * Number(drift?.opacity ?? 1),
      filter: drift?.filter ?? 'none',
    }
  })
}

defineExpose({ snapshot })
</script>

<template>
  <div class="letters" aria-hidden="true">
    <span v-for="letter in letters" :key="letter.key" class="letters__drift" :style="letter.driftStyle">
      <span ref="glyphs" :class="['letters__glyph', `is-${letter.tone}`]" :style="letter.glyphStyle">{{ glyph }}</span>
    </span>
  </div>
</template>

<style scoped>
.letters {
  position: absolute;
  inset: 0;
  overflow: hidden;
  container-type: size;
  perspective: 1000px;
}

.letters__drift {
  position: absolute;
  transform-style: preserve-3d;
  animation: drift-flat var(--period) ease-in-out var(--phase) infinite;
}

.letters__glyph {
  display: block;
  font-size: calc(var(--size) * 1cqmin);
  font-weight: 900;
  line-height: 1;
  opacity: 0;
  animation: enter-flat 700ms cubic-bezier(0.2, 0.8, 0.2, 1) var(--delay) forwards;
}

.letters__glyph.is-red {
  color: var(--color-brand);
}

.letters__glyph.is-white {
  color: #fff;
}

/* Полупрозрачная заливка, а не обводка: у вариативного Inter контуры перекрываются,
   и text-stroke рисует внутри буквы лишние линии */
.letters__glyph.is-ghost {
  color: rgb(255 255 255 / 0.18);
}

/* both, а не forwards: во время задержки перед улётом буква держит первый кадр, а не мигает */
[data-leaving] .letters__glyph {
  animation: exit-flat 360ms cubic-bezier(0.4, 0, 1, 1) var(--exit-delay) both;
}

/* Широкий экран: объём, глубина и полёт из глубины сцены */
@media (width >= 64rem) {
  .letters__drift {
    animation-name: drift-depth;
  }

  .letters__glyph {
    animation: enter-depth 1200ms cubic-bezier(0.16, 1, 0.3, 1) var(--delay) forwards;
  }

  .letters__glyph.is-ghost {
    text-shadow: 0.08em 0.12em 0.16em rgb(0 0 0 / 0.35);
  }

  [data-leaving] .letters__glyph {
    animation: exit-depth 420ms cubic-bezier(0.5, 0, 0.75, 0) var(--exit-delay) both;
  }

  .letters__glyph.is-red {
    text-shadow:
      0.01em 0.01em 0 #c42619,
      0.02em 0.02em 0 #b02217,
      0.03em 0.03em 0 #9c1e14,
      0.04em 0.04em 0 #881a11,
      0.05em 0.05em 0 #74160f,
      0.06em 0.06em 0 #60120c,
      0.08em 0.12em 0.16em rgb(0 0 0 / 0.5);
  }

  .letters__glyph.is-white {
    text-shadow:
      0.01em 0.01em 0 #dcdce2,
      0.02em 0.02em 0 #c8c8d0,
      0.03em 0.03em 0 #b4b4be,
      0.04em 0.04em 0 #a0a0ac,
      0.05em 0.05em 0 #8c8c9a,
      0.06em 0.06em 0 #787888,
      0.08em 0.12em 0.16em rgb(0 0 0 / 0.5);
  }
}

@keyframes enter-flat {
  from {
    opacity: 0;
    transform: scale(0.3) rotate(var(--from-turn));
  }
  to {
    opacity: 1;
    transform: scale(1) rotate(var(--tilt));
  }
}

@keyframes enter-depth {
  0% {
    opacity: 0;
    transform: translate3d(calc(var(--from-x) * 1cqw), calc(var(--from-y) * 1cqh), -1400px) rotateX(var(--from-rx))
      rotateY(var(--from-ry));
  }
  60% {
    opacity: 1;
  }
  100% {
    opacity: 1;
    transform: translate3d(0, 0, var(--depth)) rotateY(var(--yaw)) rotate(var(--tilt));
  }
}

@keyframes exit-flat {
  from {
    opacity: 1;
    transform: scale(1) rotate(var(--tilt));
  }
  to {
    opacity: 0;
    transform: scale(0.2) rotate(var(--from-turn));
  }
}

/* Обратно туда, откуда прилетела: в глубину сцены, с разворотом */
@keyframes exit-depth {
  from {
    opacity: 1;
    transform: translate3d(0, 0, var(--depth)) rotateY(var(--yaw)) rotate(var(--tilt));
  }
  to {
    opacity: 0;
    transform: translate3d(calc(var(--from-x) * 1cqw), calc(var(--from-y) * 1cqh), -1400px) rotateX(var(--from-rx))
      rotateY(var(--from-ry));
  }
}

@keyframes drift-flat {
  0%,
  100% {
    transform: translate(0, 0) rotate(0deg);
  }
  25% {
    transform: translate(calc(var(--dx) * 1cqmin), calc(var(--dy) * -1cqmin)) rotate(var(--rot));
  }
  50% {
    transform: translate(calc(var(--dx) * -0.5cqmin), calc(var(--dy) * 1cqmin)) rotate(0deg);
  }
  75% {
    transform: translate(calc(var(--dx) * 0.8cqmin), calc(var(--dy) * 0.4cqmin)) rotate(calc(var(--rot) * -1));
  }
}

@keyframes drift-depth {
  0%,
  100% {
    transform: translate3d(0, 0, 0) rotateY(0deg) rotate(0deg);
  }
  25% {
    transform: translate3d(calc(var(--dx) * 1cqmin), calc(var(--dy) * -1cqmin), 0) rotateY(var(--spin)) rotate(var(--rot));
  }
  50% {
    transform: translate3d(calc(var(--dx) * -0.5cqmin), calc(var(--dy) * 1cqmin), 0) rotateY(0deg) rotate(0deg);
  }
  75% {
    transform: translate3d(calc(var(--dx) * 0.8cqmin), calc(var(--dy) * 0.4cqmin), 0) rotateY(calc(var(--spin) * -1))
      rotate(calc(var(--rot) * -1));
  }
}

/* Глобальное правило сжимает анимации до 0,01 мс — бесконечный дрейф от этого мелькал бы, выключаем явно */
@media (prefers-reduced-motion: reduce) {
  .letters__drift {
    animation: none;
  }

  .letters__glyph {
    animation: none;
    opacity: 1;
    transform: rotate(var(--tilt));
  }

  [data-leaving] .letters__glyph {
    animation: none;
    opacity: 0;
  }
}
</style>
