<script setup lang="ts">
/**
 * Картинка-наклейка, которая «выглядывает» из-под карточки и время от времени
 * высовывается чуть сильнее. Без текста, только украшение.
 *
 * Как использовать: у обёртки карточек — `relative isolate`, сам стикер —
 * `absolute -z-10` и координаты так, чтобы половина картинки пряталась за карточкой.
 * `from` — с какой стороны карточки он выглядывает (туда и высовывается).
 */
export type PeekArt =
  | 'coin'
  | 'banknote'
  | 'document'
  | 'rocket'
  | 'piggy'
  | 'calculator'
  | 'chart'
  | 'question'

withDefaults(
  defineProps<{
    art: PeekArt
    from?: 'top' | 'right' | 'bottom' | 'left'
    /** Наклон в градусах */
    tilt?: number
    /** Сдвиг фазы анимации */
    delay?: number
  }>(),
  { from: 'top', tilt: 0, delay: 0 },
)
</script>

<template>
  <div
    class="peek pointer-events-none hidden size-28 select-none lg:block"
    :class="`from-${from}`"
    :style="{ rotate: `${tilt}deg`, animationDelay: `${-delay}s` }"
    aria-hidden="true"
  >
    <svg viewBox="0 0 120 120" class="size-full">
      <!-- Монета с рублём -->
      <g v-if="art === 'coin'">
        <circle cx="60" cy="60" r="50" fill="#e9a800" />
        <circle cx="60" cy="56" r="50" fill="#ffc83d" />
        <circle cx="60" cy="56" r="38" fill="none" stroke="#e9a800" stroke-width="5" />
        <text x="60" y="74" text-anchor="middle" font-size="50" font-weight="800" fill="#b37f00">₽</text>
      </g>

      <!-- Пачка купюр -->
      <g v-else-if="art === 'banknote'">
        <rect x="14" y="40" width="96" height="56" rx="10" fill="#1c9a6b" transform="rotate(-8 62 68)" />
        <rect x="10" y="30" width="96" height="56" rx="10" fill="#2ec98f" />
        <rect x="20" y="40" width="76" height="36" rx="6" fill="none" stroke="#a6f0d2" stroke-width="3" />
        <circle cx="58" cy="58" r="13" fill="#a6f0d2" />
        <text x="58" y="65" text-anchor="middle" font-size="19" font-weight="800" fill="#1c9a6b">₽</text>
      </g>

      <!-- Документ с галочкой -->
      <g v-else-if="art === 'document'">
        <path d="M26 12h48l20 20v72a6 6 0 0 1-6 6H26a6 6 0 0 1-6-6V18a6 6 0 0 1 6-6Z" fill="#ffffff" />
        <path d="M74 12v14a6 6 0 0 0 6 6h14Z" fill="#dfe6f0" />
        <rect x="32" y="42" width="40" height="6" rx="3" fill="#c9d3e3" />
        <rect x="32" y="56" width="48" height="6" rx="3" fill="#c9d3e3" />
        <rect x="32" y="70" width="28" height="6" rx="3" fill="#c9d3e3" />
        <circle cx="84" cy="88" r="20" fill="#ef3124" />
        <path d="m75 88 6 6 12-13" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" />
      </g>

      <!-- Ракета -->
      <g v-else-if="art === 'rocket'">
        <path d="M48 92c-6 8-6 18-6 22 6-2 14-6 18-12Z" fill="#ffc83d" />
        <path d="M72 92c6 8 6 18 6 22-6-2-14-6-18-12Z" fill="#ff9a3d" />
        <path d="M60 6c18 14 26 38 20 78H40C34 44 42 20 60 6Z" fill="#ef3124" />
        <path d="M40 84c-12 2-18 10-18 20l20-6Z" fill="#c2261b" />
        <path d="M80 84c12 2 18 10 18 20l-20-6Z" fill="#c2261b" />
        <circle cx="60" cy="44" r="12" fill="#fff" />
        <circle cx="60" cy="44" r="7" fill="#4d8dff" />
      </g>

      <!-- Копилка -->
      <g v-else-if="art === 'piggy'">
        <ellipse cx="58" cy="66" rx="44" ry="34" fill="#ff8fab" />
        <path d="M34 38 30 18l18 12Z" fill="#ff6f91" />
        <ellipse cx="100" cy="66" rx="10" ry="12" fill="#ff6f91" />
        <circle cx="97" cy="63" r="2.5" fill="#b8455f" />
        <circle cx="103" cy="69" r="2.5" fill="#b8455f" />
        <circle cx="80" cy="52" r="4" fill="#4a1e2a" />
        <rect x="46" y="32" width="24" height="6" rx="3" fill="#b8455f" />
        <rect x="30" y="90" width="12" height="16" rx="5" fill="#ff6f91" />
        <rect x="70" y="90" width="12" height="16" rx="5" fill="#ff6f91" />
        <circle cx="58" cy="18" r="12" fill="#ffc83d" />
        <text x="58" y="24" text-anchor="middle" font-size="16" font-weight="800" fill="#b37f00">₽</text>
      </g>

      <!-- Калькулятор -->
      <g v-else-if="art === 'calculator'">
        <rect x="20" y="8" width="80" height="104" rx="14" fill="#2b2b33" />
        <rect x="30" y="18" width="60" height="24" rx="6" fill="#a6f0d2" />
        <rect x="64" y="25" width="20" height="10" rx="3" fill="#1c9a6b" />
        <g fill="#4a4a55">
          <rect x="30" y="52" width="16" height="14" rx="4" />
          <rect x="52" y="52" width="16" height="14" rx="4" />
          <rect x="30" y="72" width="16" height="14" rx="4" />
          <rect x="52" y="72" width="16" height="14" rx="4" />
          <rect x="30" y="92" width="16" height="12" rx="4" />
          <rect x="52" y="92" width="16" height="12" rx="4" />
        </g>
        <rect x="74" y="52" width="16" height="34" rx="4" fill="#ffc83d" />
        <rect x="74" y="92" width="16" height="12" rx="4" fill="#ef3124" />
      </g>

      <!-- График роста -->
      <g v-else-if="art === 'chart'">
        <rect x="8" y="8" width="104" height="104" rx="20" fill="#4d8dff" />
        <rect x="24" y="70" width="14" height="26" rx="4" fill="#a9c8ff" />
        <rect x="46" y="56" width="14" height="40" rx="4" fill="#a9c8ff" />
        <rect x="68" y="44" width="14" height="52" rx="4" fill="#a9c8ff" />
        <path d="M22 62 46 44l16 10 30-28" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M78 22h16v16" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
      </g>

      <!-- Облачко с вопросом -->
      <g v-else-if="art === 'question'">
        <path d="M60 10c28 0 50 18 50 42S88 94 60 94c-6 0-12-1-17-2l-23 16 6-24C16 76 10 64 10 52 10 28 32 10 60 10Z" fill="#ffc83d" />
        <text x="60" y="72" text-anchor="middle" font-size="58" font-weight="800" fill="#3a2a00">?</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.peek {
  /* Белая кромка вокруг рисунка и мягкая тень — как у вырезанной наклейки */
  filter: drop-shadow(3px 0 0 white) drop-shadow(-3px 0 0 white) drop-shadow(0 3px 0 white)
    drop-shadow(0 -3px 0 white) drop-shadow(0 10px 14px rgb(30 43 68 / 0.18));
  animation: peek 5s ease-in-out infinite;
}

/* Направление, в котором стикер высовывается из-за карточки */
.peek.from-top {
  --dx: 0;
  --dy: -14px;
}

.peek.from-bottom {
  --dx: 0;
  --dy: 14px;
}

.peek.from-left {
  --dx: -14px;
  --dy: 0;
}

.peek.from-right {
  --dx: 14px;
  --dy: 0;
}

@keyframes peek {
  0%,
  55%,
  100% {
    transform: translate(0, 0) rotate(0deg);
  }
  70% {
    transform: translate(var(--dx), var(--dy)) rotate(-6deg);
  }
  80% {
    transform: translate(var(--dx), var(--dy)) rotate(5deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .peek {
    animation: none;
  }
}
</style>
