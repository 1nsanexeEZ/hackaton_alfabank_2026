<script setup lang="ts">
import { ArrowUp, FileText, LoaderCircle, Maximize2, Minimize2, RotateCcw, ShieldCheck, Sparkles, SquarePen, TriangleAlert, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

import { assistant, ASSISTANT_AVAILABILITY_LABEL, ASSISTANT_MAX_QUESTION } from '@/entities/assistant'
import { customer } from '@/entities/customer'

import ApplicationPicker from './ApplicationPicker.vue'

/**
 * Окно «Умный помощник»: панель справа поверх любой страницы сайта (на телефоне — на весь экран).
 * Открывается кнопкой в шапке (entities/assistant), закрывается по Esc, крестику и клику вне окна.
 * Вход и переход к заявке окно не решает само — отдаёт событиями странице, как шапка.
 */
const emit = defineEmits<{ login: []; 'open-application': [id: string] }>()

const QUICK_QUESTIONS = [
  'Что решил банк по заявке?',
  'Где сейчас моя заявка?',
  'Какие кредиты подойдут?',
  'Что улучшить, чтобы одобрили?',
] as const

const state = assistant.state
const id = useId()
const panel = ref<HTMLElement>()
const log = ref<HTMLElement>()
const field = ref<HTMLTextAreaElement>()
const draft = ref('')

const isOff = computed(() => state.availability === 'off')
const isEmpty = computed(() => state.messages.length === 0)
const length = computed(() => draft.value.trim().length)
const tooLong = computed(() => length.value > ASSISTANT_MAX_QUESTION)
const canSend = computed(() => length.value > 0 && !tooLong.value && !state.busy && !isOff.value)
const showOffState = computed(() => isOff.value && isEmpty.value && !state.loading)
/** Ошибка последнего действия; сервис пропал посреди диалога — напоминаем об этом и даём «Повторить» */
const banner = computed(() => {
  if (showOffState.value) return null
  if (state.error) return state.error
  return isOff.value && !isEmpty.value ? { kind: 'unavailable' as const, message: 'Помощник временно недоступен', retryAfter: null } : null
})
const showRetry = computed(() => banner.value?.kind === 'unavailable' || banner.value?.kind === 'rate_limited')

const subtitle = computed(() => ASSISTANT_AVAILABILITY_LABEL[state.availability])

function applicationNumber(applicationId: string | null): string | null {
  return state.applications.find((item) => item.id === applicationId)?.number ?? null
}

function resizeField() {
  const el = field.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 144)}px`
}

function submit(text = draft.value) {
  if (state.busy || isOff.value || !text.trim()) return
  const wasDraft = text === draft.value
  void assistant.send(text)
  if (wasDraft) {
    draft.value = ''
    void nextTick(resizeField)
  }
}

function onFieldKeydown(event: KeyboardEvent) {
  // Enter отправляет, Shift+Enter — перенос строки; во время набора через IME Enter не трогаем
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  if (canSend.value) submit()
}

function signIn() {
  customer.logout()
  assistant.close()
  emit('login')
}

function newDialog() {
  assistant.newDialog()
  void nextTick(() => field.value?.focus({ preventScroll: true }))
}

// --- Ширина окна: кнопка «Развернуть» и перетаскивание левого края; на телефоне окно и так во весь экран ---

const WIDTH_KEY = 'assistant.width'
const NARROW = 448
const WIDE = 896
const MIN_WIDTH = 384

const width = ref(readWidth())
const resizing = ref(false)
const isWide = computed(() => width.value > (NARROW + WIDE) / 2)

function maxWidth(): number {
  return Math.max(MIN_WIDTH, window.innerWidth - 48)
}

function clampWidth(value: number): number {
  return Math.round(Math.min(Math.max(value, MIN_WIDTH), maxWidth()))
}

function readWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_KEY))
    return saved > 0 ? saved : NARROW
  } catch {
    return NARROW
  }
}

function saveWidth() {
  try {
    localStorage.setItem(WIDTH_KEY, String(width.value))
  } catch {
    // без хранилища ширина просто не запомнится
  }
}

const panelWidth = computed(() => `${Math.min(width.value, maxWidth())}px`)

function toggleWide() {
  width.value = isWide.value ? NARROW : clampWidth(WIDE)
  saveWidth()
}

function onResizeMove(event: PointerEvent) {
  width.value = clampWidth(window.innerWidth - event.clientX)
}

function onResizeEnd() {
  resizing.value = false
  document.removeEventListener('pointermove', onResizeMove)
  document.removeEventListener('pointerup', onResizeEnd)
  saveWidth()
}

function onResizeStart(event: PointerEvent) {
  event.preventDefault()
  resizing.value = true
  document.addEventListener('pointermove', onResizeMove)
  document.addEventListener('pointerup', onResizeEnd)
}

/** Стрелками с клавиатуры — тот же ресайз для тех, кто не тянет мышью */
function onResizeKey(event: KeyboardEvent) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  width.value = clampWidth(width.value + (event.key === 'ArrowLeft' ? 48 : -48))
  saveWidth()
}

// --- Прокрутка: к новому сообщению и за потоком ответа, если клиент не листал вверх ---

function scrollToEnd(force = false) {
  const el = log.value
  if (!el) return
  const nearEnd = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  if (force || nearEnd) el.scrollTop = el.scrollHeight
}

watch(
  () => state.messages.length,
  async () => {
    await nextTick()
    scrollToEnd(true)
  },
)

watch(
  () => state.messages[state.messages.length - 1]?.text,
  async () => {
    await nextTick()
    scrollToEnd()
  },
)

// --- Фокус и блокировка страницы ---

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
let returnFocusTo: HTMLElement | null = null

function focusables(): HTMLElement[] {
  return panel.value ? [...panel.value.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null) : []
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    assistant.close()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus({ preventScroll: true })
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus({ preventScroll: true })
  } else if (!panel.value?.contains(document.activeElement)) {
    event.preventDefault()
    first.focus({ preventScroll: true })
  }
}

/** Куда вернуть фокус: на то, чем открыли; кнопки уже нет (мобильное меню закрылось) — на кнопку в шапке */
function restoreFocus() {
  const target = returnFocusTo?.isConnected ? returnFocusTo : null
  const fallback = [...document.querySelectorAll<HTMLElement>('[data-assistant-trigger]')].find((el) => el.offsetParent !== null)
  ;(target ?? fallback)?.focus({ preventScroll: true })
  returnFocusTo = null
}

watch(
  () => state.open,
  async (isOpen) => {
    if (isOpen) {
      returnFocusTo = document.activeElement as HTMLElement | null
      document.addEventListener('keydown', onKeydown)
      document.body.style.overflow = 'hidden'
      await nextTick()
      field.value?.focus({ preventScroll: true })
      if (!field.value || document.activeElement !== field.value) focusables().find((el) => !el.hasAttribute('data-close'))?.focus({ preventScroll: true })
    } else {
      document.removeEventListener('keydown', onKeydown)
      document.body.style.overflow = ''
      restoreFocus()
    }
  },
)

// Загрузилось, и поле появилось — ставим туда курсор (при открытии оно могло быть ещё недоступно)
watch(
  () => state.loading,
  async (loading) => {
    if (loading || !state.open) return
    await nextTick()
    scrollToEnd(true)
    if (!panel.value?.contains(document.activeElement) || document.activeElement === panel.value) field.value?.focus({ preventScroll: true })
  },
)

// Вышли из кабинета или сменили учётку: диалог и заявки предыдущего клиента не остаются
watch(
  () => customer.state.me?.id ?? null,
  (current, previous) => {
    if (previous && current !== previous) assistant.reset()
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointermove', onResizeMove)
  document.removeEventListener('pointerup', onResizeEnd)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="assistant" :duration="{ enter: 360, leave: 260 }">
      <div v-if="state.open" class="assistant fixed inset-0 z-[100]">
        <div class="assistant__backdrop absolute inset-0 cursor-pointer" aria-hidden="true" @click="assistant.close()" />

        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`${id}-title`"
          :aria-describedby="`${id}-note`"
          class="assistant__panel absolute inset-0 flex flex-col overflow-hidden text-on-night shadow-2xl sm:left-auto sm:w-[var(--assistant-width)] sm:max-w-full sm:rounded-l-[2rem]"
          :class="{ 'select-none': resizing }"
          :style="{ '--assistant-width': panelWidth }"
        >
          <!-- Левый край: тянуть, чтобы расширить окно -->
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Ширина окна помощника"
            :aria-valuenow="Math.min(width, maxWidth())"
            :aria-valuemin="MIN_WIDTH"
            tabindex="0"
            class="assistant__resize absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize max-sm:hidden"
            :data-active="resizing || undefined"
            @pointerdown="onResizeStart"
            @dblclick="toggleWide"
            @keydown="onResizeKey"
          />
          <!-- Шапка: логотип, название, состояние, «Новый диалог», закрыть -->
          <header class="flex items-center gap-3 px-5 pt-5 pb-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand text-lg font-extrabold text-white" aria-hidden="true">А</span>
            <div class="min-w-0 flex-1">
              <h2 :id="`${id}-title`" class="truncate text-base leading-tight font-bold">Умный помощник</h2>
              <p class="mt-0.5 flex items-center gap-1.5 text-xs text-on-night-secondary" aria-live="polite">
                <span class="assistant__dot size-1.5 shrink-0 rounded-full" :data-state="state.availability" aria-hidden="true" />
                {{ subtitle }}
              </p>
            </div>
            <button
              type="button"
              class="flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-night-glass px-3 text-xs font-medium text-on-night transition-colors hover:bg-white/15 disabled:opacity-50 max-sm:w-9 max-sm:justify-center max-sm:px-0"
              aria-label="Новый диалог"
              :disabled="isEmpty && !state.conversationId"
              @click="newDialog"
            >
              <SquarePen class="size-3.5" aria-hidden="true" />
              <span class="max-sm:hidden">Новый диалог</span>
            </button>
            <button
              type="button"
              class="flex size-9 shrink-0 items-center justify-center rounded-full bg-night-glass text-on-night transition-colors hover:bg-white/15 max-sm:hidden"
              :aria-label="isWide ? 'Сузить окно помощника' : 'Развернуть окно помощника'"
              :title="isWide ? 'Сузить' : 'Развернуть'"
              @click="toggleWide"
            >
              <Minimize2 v-if="isWide" class="size-4" aria-hidden="true" />
              <Maximize2 v-else class="size-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              data-close
              class="flex size-9 shrink-0 items-center justify-center rounded-full bg-night-glass text-on-night transition-colors hover:bg-white/15"
              aria-label="Закрыть окно помощника"
              @click="assistant.close()"
            >
              <X class="size-[18px]" aria-hidden="true" />
            </button>
          </header>


          <!-- Выбор заявки, о которой спрашиваем -->
          <div v-if="state.applications.length && !isOff" class="px-5 pb-3">
            <ApplicationPicker :applications="state.applications" :selected-id="state.applicationId" @select="assistant.selectApplication" />
          </div>

          <!-- Диалог -->
          <div ref="log" role="log" aria-live="polite" aria-label="Диалог с помощником" class="assistant__log flex-1 overflow-y-auto px-5 py-2" tabindex="-1">
            <div v-if="state.loading && isEmpty" class="flex h-full flex-col items-center justify-center gap-3 text-sm text-on-night-secondary">
              <LoaderCircle class="size-6 animate-spin" aria-hidden="true" />
              Загружаем помощника…
            </div>

            <div v-else-if="showOffState" class="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
              <span class="flex size-14 items-center justify-center rounded-2xl bg-night-glass text-on-night-secondary">
                <TriangleAlert class="size-7" aria-hidden="true" />
              </span>
              <div>
                <p class="text-base font-semibold">Помощник временно недоступен</p>
                <p class="mt-1.5 text-sm text-on-night-secondary">
                  Решение по заявке от этого не меняется: статус и условия — в кабинете. Попробуйте ещё раз чуть позже.
                </p>
              </div>
              <button
                type="button"
                class="flex h-10 items-center gap-2 rounded-full bg-brand px-5 text-sm font-medium text-white transition-colors hover:bg-brand-hover"
                @click="assistant.retry()"
              >
                <RotateCcw class="size-4" aria-hidden="true" />
                Повторить
              </button>
            </div>

            <div v-else-if="isEmpty" class="flex h-full flex-col justify-center gap-3 pb-6">
              <p class="text-lg font-semibold">Здравствуйте! Чем помочь?</p>
              <p class="text-sm text-on-night-secondary">
                Объясню решение банка, подскажу, на каком этапе заявка и что можно улучшить, прикину платёж по сумме и сроку.
              </p>
            </div>

            <ul v-else class="flex flex-col gap-3 py-2">
              <li v-for="message in state.messages" :key="message.id" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
                <div
                  v-if="message.role === 'user'"
                  class="max-w-[85%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line text-white"
                >
                  {{ message.text }}
                  <p v-if="message.failed" class="mt-1 text-xs text-white/80">Не отправлено</p>
                </div>

                <div v-else class="max-w-[92%] rounded-2xl rounded-bl-md border border-night-line bg-night-glass px-4 py-3 text-sm leading-relaxed">
                  <p v-if="message.streaming && !message.text" class="assistant__typing flex items-center gap-1 py-1 text-on-night-secondary" aria-label="Помощник думает">
                    <span /><span /><span />
                  </p>
                  <p v-else class="whitespace-pre-line">
                    {{ message.text }}<span v-if="message.streaming" class="assistant__caret" aria-hidden="true" />
                  </p>
                  <template v-if="!message.streaming">
                    <button
                      v-if="message.applicationId && applicationNumber(message.applicationId)"
                      type="button"
                      class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-soft underline decoration-white/30 underline-offset-2 hover:decoration-white"
                      @click="emit('open-application', message.applicationId)"
                    >
                      Открыть заявку № {{ applicationNumber(message.applicationId) }}
                    </button>
                    <p v-if="message.mode === 'llm'" class="mt-2 flex items-center gap-1.5 text-[11px] text-on-night-secondary">
                      <ShieldCheck class="size-3.5 shrink-0 text-signal-ok" aria-hidden="true" />
                      Ответ ИИ · суммы сверены с данными банка
                    </p>
                    <p v-else-if="message.mode === 'rules'" class="mt-2 flex items-center gap-1.5 text-[11px] text-on-night-secondary">
                      <FileText class="size-3.5 shrink-0 text-signal-warn" aria-hidden="true" />
                      Ответ по шаблону
                    </p>
                  </template>
                </div>
              </li>
            </ul>
          </div>

          <!-- Ошибка последнего действия -->
          <div
            v-if="banner"
            role="alert"
            class="mx-5 mb-2 flex items-start gap-2.5 rounded-xl border border-brand/40 bg-brand/10 px-3.5 py-2.5 text-sm"
          >
            <TriangleAlert class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
            <p class="flex-1">{{ banner.message }}</p>
            <button v-if="banner.kind === 'unauthorized'" type="button" class="shrink-0 font-semibold text-brand-soft underline underline-offset-2" @click="signIn">Войти</button>
            <button v-else-if="showRetry" type="button" class="shrink-0 font-semibold text-brand-soft underline underline-offset-2" @click="assistant.retry()">Повторить</button>
          </div>

          <!-- Быстрые вопросы -->
          <div
            v-if="!showOffState && !(state.loading && isEmpty)"
            class="flex flex-wrap gap-2 px-5 pb-2"
          >
            <button
              v-for="question in QUICK_QUESTIONS"
              :key="question"
              type="button"
              class="shrink-0 rounded-full border border-night-line bg-night-glass px-3.5 py-2 text-left text-[13px] leading-tight text-on-night transition-colors hover:border-brand/60 hover:bg-brand/15 disabled:opacity-50"
              :disabled="state.busy || isOff"
              @click="submit(question)"
            >
              {{ question }}
            </button>
          </div>

          <!-- Поле ввода -->
          <form class="px-5 pt-1 pb-4" @submit.prevent="submit()">
            <div
              class="assistant__field flex items-end gap-2 rounded-2xl border bg-night-glass p-2 pl-3.5 transition-colors"
              :class="tooLong ? 'border-brand' : 'border-night-line focus-within:border-white/40'"
            >
              <textarea
                ref="field"
                v-model="draft"
                rows="1"
                :disabled="isOff"
                :placeholder="isOff ? 'Помощник сейчас недоступен' : 'Спросите про заявку или кредит'"
                aria-label="Вопрос помощнику"
                :aria-invalid="tooLong"
                class="max-h-36 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-sm text-on-night placeholder:text-on-night-secondary focus:outline-none disabled:opacity-60"
                @input="resizeField"
                @keydown="onFieldKeydown"
              />
              <button
                type="submit"
                class="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand text-white transition-colors hover:bg-brand-hover disabled:bg-night-glass disabled:text-on-night-secondary"
                :disabled="!canSend"
                aria-label="Отправить вопрос"
              >
                <LoaderCircle v-if="state.busy" class="size-4 animate-spin" aria-hidden="true" />
                <ArrowUp v-else class="size-[18px]" aria-hidden="true" />
              </button>
            </div>
            <div class="mt-1.5 flex items-start justify-between gap-3 px-1 text-[11px] leading-snug text-on-night-secondary">
              <p v-if="tooLong" class="text-brand-soft">Сократите вопрос до {{ ASSISTANT_MAX_QUESTION }} символов</p>
              <p v-else :id="`${id}-note`" class="flex items-start gap-1.5">
                <Sparkles class="mt-px size-3 shrink-0 text-brand" aria-hidden="true" />
                Помощник объясняет и подсказывает, но не принимает решений. Суммы и ставки — из данных банка.
              </p>
              <span class="shrink-0 tabular-nums" :class="tooLong ? 'text-brand-soft' : ''" aria-hidden="true">{{ length }} / {{ ASSISTANT_MAX_QUESTION }}</span>
            </div>
            <span v-if="tooLong" :id="`${id}-note`" class="sr-only">Помощник объясняет и подсказывает, но не принимает решений.</span>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.assistant__backdrop {
  background: rgb(18 18 19 / 0.55);
}

/* «Ночной эфир»: красно-чёрный градиент, красное свечение сверху справа и снизу слева */
.assistant__panel {
  background:
    radial-gradient(120% 55% at 100% 0%, color-mix(in srgb, var(--color-brand) 30%, transparent), transparent 65%),
    radial-gradient(90% 45% at 0% 100%, color-mix(in srgb, var(--color-brand) 16%, transparent), transparent 65%),
    var(--color-night);
  border-left: 1px solid var(--color-night-line);
}

.assistant__dot {
  background: var(--color-signal-off);
}

.assistant__dot[data-state='llm'] {
  background: var(--color-signal-ok);
}

.assistant__dot[data-state='rules'] {
  background: var(--color-signal-warn);
}

/* Ручка ресайза: тонкая полоса у левого края, подсвечивается при наведении и перетаскивании */
.assistant__resize::after {
  content: '';
  position: absolute;
  inset: 50% auto auto 3px;
  width: 3px;
  height: 3rem;
  border-radius: 999px;
  background: var(--color-night-line);
  transform: translateY(-50%);
  transition: background-color 150ms;
}

.assistant__resize:hover::after,
.assistant__resize:focus-visible::after,
.assistant__resize[data-active]::after {
  background: var(--color-brand);
}

.assistant__resize:focus-visible {
  outline: none;
}

.assistant__log {
  scrollbar-width: thin;
  scrollbar-color: var(--color-night-line) transparent;
}

/* Помощник думает: три точки */
.assistant__typing span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
  animation: assistant-dot 1.2s ease-in-out infinite;
}

.assistant__typing span:nth-child(2) {
  animation-delay: 0.15s;
}

.assistant__typing span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes assistant-dot {
  0%,
  60%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

/* Курсор у печатающегося текста */
.assistant__caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--color-brand);
  animation: assistant-caret 0.9s steps(2) infinite;
}

@keyframes assistant-caret {
  50% {
    opacity: 0;
  }
}

.assistant-enter-active .assistant__backdrop,
.assistant-leave-active .assistant__backdrop {
  transition: opacity 260ms ease-out;
}

.assistant-enter-active .assistant__panel {
  transition: transform 360ms cubic-bezier(0.22, 1, 0.36, 1);
}

.assistant-leave-active .assistant__panel {
  transition: transform 260ms cubic-bezier(0.4, 0, 0.2, 1);
}

.assistant-enter-from .assistant__backdrop,
.assistant-leave-to .assistant__backdrop {
  opacity: 0;
}

.assistant-enter-from .assistant__panel,
.assistant-leave-to .assistant__panel {
  transform: translateX(100%);
}

@media (width < 40rem) {
  .assistant-enter-from .assistant__panel,
  .assistant-leave-to .assistant__panel {
    transform: translateY(8%);
    opacity: 0;
  }

  .assistant__panel {
    border-left: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .assistant__typing span,
  .assistant__caret {
    animation: none;
  }
}
</style>
