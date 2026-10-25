<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

type Variant = 'primary' | 'secondary' | 'ghost' | 'inverted' | 'glass'
type Size = 's' | 'm' | 'l'

const props = withDefaults(
  defineProps<{
    variant?: Variant
    size?: Size
    /** Внешняя ссылка или якорь — рендерится <a> */
    href?: string
    /** Маршрут приложения — рендерится RouterLink */
    to?: RouteLocationRaw
    type?: 'button' | 'submit' | 'reset'
    block?: boolean
    disabled?: boolean
    loading?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'm',
    href: undefined,
    to: undefined,
    type: 'button',
    block: false,
    disabled: false,
    loading: false,
  },
)

const VARIANT_CLASS: Record<Variant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-hover active:bg-brand-active',
  secondary: 'bg-surface text-ink',
  ghost: 'text-ink hover:bg-surface',
  // Белая кнопка на тёмном фоне
  inverted: 'bg-white text-ink',
  // Второстепенная кнопка на тёмном фоне
  glass: 'text-on-night',
}

const SIZE_CLASS: Record<Size, string> = {
  s: 'h-10 px-4 text-sm',
  m: 'h-12 px-5 text-base',
  l: 'h-14 px-7 text-base',
}

/*
 * Движение у каждого варианта своё, чтобы кнопки звали нажать, но не спорили друг с другом:
 * главная — блик, дышащее кольцо, увеличение с пружиной и искры по клику;
 * второстепенная — тёмная заливка слева; стеклянная — бегущая подсветка контура;
 * белая и прозрачная — текст прокручивается вверх. У всех — волна от клика и сжатие при нажатии.
 */
const SPARK_COLORS = ['#ef3124', '#ffd03d', '#4d8dff', '#2ec98f', '#ffffff']

const tag = computed(() => (props.to ? RouterLink : props.href ? 'a' : 'button'))

const tagAttrs = computed(() => {
  if (props.to) return { to: props.to }
  if (props.href) return { href: props.href }
  return { type: props.type, disabled: props.disabled || props.loading }
})

const isInactive = computed(() => props.disabled || props.loading)
const rolls = computed(() => props.variant === 'inverted' || props.variant === 'ghost')

const reducedMotion =
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

interface Burst {
  id: number
  style: Record<string, string>
}

let seq = 0
const timers = new Set<ReturnType<typeof setTimeout>>()

function later(fn: () => void, ms: number) {
  const timer = setTimeout(() => {
    timers.delete(timer)
    fn()
  }, ms)
  timers.add(timer)
}

onBeforeUnmount(() => timers.forEach(clearTimeout))

const ripples = ref<Burst[]>([])
const sparks = ref<Burst[]>([])

function onPointerDown(event: PointerEvent) {
  if (isInactive.value || reducedMotion) return
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const id = ++seq
  ripples.value.push({ id, style: { left: `${event.clientX - rect.left}px`, top: `${event.clientY - rect.top}px` } })
  later(() => (ripples.value = ripples.value.filter((item) => item.id !== id)), 700)
}

function onClick() {
  if (props.variant !== 'primary' || isInactive.value || reducedMotion) return
  const base = ++seq * 100
  sparks.value = Array.from({ length: 12 }, (_, index) => {
    const angle = (index / 12) * Math.PI * 2
    const distance = 52 + (index % 3) * 18
    return {
      id: base + index,
      style: {
        background: SPARK_COLORS[index % SPARK_COLORS.length]!,
        '--sx': `${Math.round(Math.cos(angle) * distance)}px`,
        '--sy': `${Math.round(Math.sin(angle) * distance * 0.7)}px`,
      },
    }
  })
  later(() => (sparks.value = sparks.value.filter((item) => item.id < base || item.id >= base + 12)), 800)
}
</script>

<template>
  <component
    :is="tag"
    v-bind="tagAttrs"
    :aria-busy="loading || undefined"
    :class="[
      'btn relative isolate inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap select-none',
      'disabled:pointer-events-none disabled:opacity-50',
      `btn--${variant}`,
      VARIANT_CLASS[variant],
      SIZE_CLASS[size],
      block && 'w-full',
    ]"
    @pointerdown="onPointerDown"
    @click="onClick"
  >
    <!-- Слой эффектов: обрезан по форме кнопки, сама кнопка не обрезает искры -->
    <span class="btn__clip pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-[inherit]" aria-hidden="true">
      <span v-for="ripple in ripples" :key="ripple.id" class="btn__ripple" :style="ripple.style" />
    </span>

    <span
      v-if="loading"
      class="size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden="true"
    />

    <!-- Прокрутка текста: снизу выезжает копия надписи -->
    <span v-if="rolls" class="btn__roll">
      <span class="btn__label"><slot /></span>
      <span class="btn__label" aria-hidden="true"><slot /></span>
    </span>
    <slot v-else />

    <span v-for="spark in sparks" :key="spark.id" class="btn__spark" :style="spark.style" aria-hidden="true" />
  </component>
</template>

<style scoped>
.btn {
  --spring: cubic-bezier(0.22, 1, 0.36, 1);

  transition:
    scale 0.2s var(--spring),
    background-color 0.25s,
    color 0.3s,
    box-shadow 0.3s;
}

.btn:active {
  scale: 0.95;
}

/*
 * Блик: светлая полоса пробегает раз в несколько секунд и сразу — при наведении.
 * Двигается transform, а не left: полоса едет на композиторе и не перерисовывает кнопку каждый кадр.
 * Ширина полосы — 40% кнопки, поэтому -150% и 325% её ширины — это -60% и 130% кнопки.
 */
.btn--primary .btn__clip::before,
.btn--inverted .btn__clip::before {
  content: '';
  position: absolute;
  inset: -20% auto -20% 0;
  width: 40%;
  background: linear-gradient(100deg, transparent, rgb(255 255 255 / 0.5), transparent);
  transform: translateX(-150%) skewX(-20deg);
  animation: btn-glint 5s ease-in-out infinite;
}

.btn--inverted .btn__clip::before {
  background: linear-gradient(100deg, transparent, rgb(18 18 19 / 0.08), transparent);
}

.btn--primary:hover .btn__clip::before,
.btn--inverted:hover .btn__clip::before {
  animation: btn-glint-once 0.7s ease-out;
}

@keyframes btn-glint {
  0%,
  72% {
    transform: translateX(-150%) skewX(-20deg);
  }
  88%,
  100% {
    transform: translateX(325%) skewX(-20deg);
  }
}

@keyframes btn-glint-once {
  from {
    transform: translateX(-150%) skewX(-20deg);
  }
  to {
    transform: translateX(325%) skewX(-20deg);
  }
}

/*
 * Дышащее кольцо главной кнопки; при наведении сменяется тенью. Кольцо — отдельный слой, который
 * растёт и гаснет (transform и opacity), а не анимированный box-shadow: тот перерисовывал кнопку
 * каждый кадр. Слой красный, как кнопка, поэтому поверх её фона его не видно — только снаружи.
 */
.btn--primary::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -20;
  border-radius: inherit;
  background: rgb(239 49 36 / 0.4);
  opacity: 0;
  pointer-events: none;
  animation: btn-pulse 2.6s ease-out infinite;
}

/*
 * Наведение: кнопка увеличивается с лёгкой пружиной, по ней пробегает блик и снизу разгорается
 * красное свечение. scale не меняет размер в потоке — соседние элементы остаются на месте.
 */
.btn--primary:hover:not(:active)::after {
  animation: none;
}

.btn--primary:hover:not(:active) {
  scale: 1.05;
  transition-duration: 0.45s;
  transition-timing-function: cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow:
    0 0.875rem 1.875rem rgb(239 49 36 / 0.35),
    0 0 0 0.25rem rgb(239 49 36 / 0.12);
}

.btn--primary:disabled::after,
.btn--primary[aria-busy='true']::after {
  animation: none;
}

/* Кольцо шире по высоте, чем по ширине: так у кнопки обычных пропорций оно расходится почти равномерно */
@keyframes btn-pulse {
  0% {
    opacity: 1;
    transform: scale(1);
  }
  70%,
  100% {
    opacity: 0;
    transform: scale(1.12, 1.55);
  }
}

/*
 * В окнах и панелях кнопки не дышат и блик не бегает сам: там договор и подпись, движение
 * отвлекает, а постоянная перерисовка внутри прокрутки заставляла кнопки отставать от окна.
 * Реакция на наведение и нажатие остаётся.
 */
:where([role='dialog']) .btn--primary::after,
:where([role='dialog']) .btn--primary .btn__clip::before,
:where([role='dialog']) .btn--inverted .btn__clip::before,
:where([role='dialog']) .btn--glass .btn__clip::before {
  animation: none;
}

/* Второстепенная: тёмная заливка выезжает слева, иконка покачивается */
.btn--secondary .btn__clip::after {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--color-night);
  transform: scaleX(0);
  transform-origin: right;
  transition: transform 0.45s cubic-bezier(0.7, 0, 0.2, 1);
}

.btn--secondary:hover {
  color: var(--color-on-night);
}

.btn--secondary:hover .btn__clip::after {
  transform: scaleX(1);
  transform-origin: left;
}

.btn--secondary:hover :deep(svg) {
  animation: btn-wiggle 0.6s ease-in-out;
}

@keyframes btn-wiggle {
  25% {
    rotate: -14deg;
  }
  50% {
    rotate: 12deg;
  }
  75% {
    rotate: -6deg;
  }
}

/* Стеклянная: по контуру бежит световая точка — вращается конический градиент под кнопкой */
.btn--glass .btn__clip::before {
  content: '';
  position: absolute;
  inset: -150%;
  background: conic-gradient(from 0deg, transparent 0 70%, rgb(255 255 255 / 0.85) 82%, transparent 94%);
  animation: btn-orbit 3.4s linear infinite;
}

.btn--glass .btn__clip::after {
  content: '';
  position: absolute;
  inset: 1.5px;
  border-radius: inherit;
  background: rgb(38 38 42 / 0.94);
  transition: background-color 0.25s;
}

.btn--glass:hover .btn__clip::before {
  animation-duration: 1.2s;
}

.btn--glass:hover .btn__clip::after {
  background: rgb(52 52 58 / 0.94);
}

@keyframes btn-orbit {
  to {
    rotate: 1turn;
  }
}

/* Белая на тёмном */
.btn--inverted:hover {
  box-shadow: 0 0.75rem 1.75rem rgb(0 0 0 / 0.3);
}

/* Прокрутка надписи: оригинал уезжает вверх, копия выезжает снизу */
.btn__roll {
  display: inline-grid;
  overflow: hidden;
}

.btn__label {
  grid-area: 1 / 1;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: transform 0.45s cubic-bezier(0.7, 0, 0.2, 1);
}

.btn__label + .btn__label {
  transform: translateY(110%);
}

.btn:hover .btn__label:first-child {
  transform: translateY(-110%);
}

.btn:hover .btn__label + .btn__label {
  transform: none;
}

/* Волна от точки нажатия */
.btn__ripple {
  position: absolute;
  width: 0.75rem;
  height: 0.75rem;
  margin: -0.375rem 0 0 -0.375rem;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.3;
  animation: btn-ripple 0.7s ease-out forwards;
}

@keyframes btn-ripple {
  to {
    transform: scale(40);
    opacity: 0;
  }
}

/* Искры от главной кнопки */
.btn__spark {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0.4375rem;
  height: 0.4375rem;
  border-radius: 2px;
  pointer-events: none;
  animation: btn-spark 0.75s var(--spring) forwards;
}

@keyframes btn-spark {
  from {
    transform: translate(-50%, -50%) rotate(0) scale(1);
    opacity: 1;
  }
  to {
    transform: translate(var(--sx), var(--sy)) rotate(220deg) scale(0.4);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn,
  .btn *,
  .btn__clip::before,
  .btn__clip::after {
    animation: none !important;
  }
}
</style>
