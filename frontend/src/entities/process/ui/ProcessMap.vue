<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, useId, watch } from 'vue'

import type { ProcessDto, ProcessStepDto } from '@/shared/api'
import { formatDateTime, formatDuration, formatTime, pluralize } from '@/shared/lib'
import { BaseBadge, BaseButton, PanelCard, type BadgeTone } from '@/shared/ui'

import { columnWidth, hopLine, lineLength, mapGeometry, pointAlong, roundedPath, STAGE_RADIUS, type Point } from '../model/geometry'
import { emptyProgress, withPrelude, withPreludeProgress, type PreludeStage } from '../model/prelude'
import { processProgress, type StageProgress, type StageState, type StageWindow, type WaitingFor } from '../model/progress'
import type { Stage, StageKey } from '../model/stages'
import { useProcessTracking } from '../model/useProcessTracking'

/**
 * Маршрут заявки по этапам в реальном времени: красная точка идёт по этапам, которые проходит
 * процесс, клик по этапу показывает подробности. Что показать про этап из карточки заявки —
 * решает тот, кто встраивает схему, через слот details. prelude — этапы до подачи (согласия,
 * предскоринг), они встают в начало; fallbackWorkflow — маршрут продукта, по нему схема строится
 * у черновика, пока процесса нет. В шапке — версия BPMN-маршрута и, если по заявке уже решали,
 * версия кредитной политики (policyVersion): это разные версии, у маршрута своя нумерация.
 */
const props = withDefaults(
  defineProps<{
    applicationId: string
    prelude?: readonly PreludeStage[]
    fallbackWorkflow?: string | null
    /** policy_v8 — по какой политике принято решение */
    policyVersion?: string | null
  }>(),
  { prelude: () => [], fallbackWorkflow: null, policyVersion: null },
)
const emit = defineEmits<{ advance: [process: ProcessDto] }>()

defineSlots<{
  /** windows — когда заявка была на этапе: по ним события карточки раскладываются по этапам */
  details?: (props: { stage: StageKey; state: StageState; windows: readonly StageWindow[] }) => unknown
  footer?: () => unknown
}>()

const tracking = useProcessTracking(() => props.applicationId, {
  onAdvance: (process) => emit('advance', process),
  fallbackWorkflow: () => props.fallbackWorkflow,
})
const { process, graph: routeGraph, loading, missing, error, now } = tracking
defineExpose({ refresh: tracking.refresh })

/** Маршрут с этапами до подачи в начале */
const graph = computed(() => (routeGraph.value ? withPrelude(routeGraph.value, props.prelude) : null))

/** «Стандартный: … · маршрут v2 · политика v8»; у черновика версия маршрута — из кода (standard_v2) */
const description = computed(() => {
  if (!graph.value) return undefined
  const route = process.value?.workflow_version ?? /_v(\d+)$/.exec(graph.value.workflow.code)?.[1]
  const policy = props.policyVersion?.replace(/^policy_/, '')
  return [graph.value.workflow.name, route && `маршрут v${route}`, policy && `политика ${policy}`].filter(Boolean).join(' · ')
})

const progress = computed(() => {
  const route = routeGraph.value
  if (!route) return null
  const base = process.value ? processProgress(route, process.value, now.value) : emptyProgress(route)
  return withPreludeProgress(base, props.prelude, route.start)
})

const isPrelude = (key: StageKey) => key.startsWith('pre:')
const preludeNote = computed(() => new Map(props.prelude.map((item) => [item.key as StageKey, item.note])))

// Колонки растягиваем под ширину панели; на узком экране схема прокручивается внутри панели
const scroller = ref<HTMLElement | null>(null)
const containerWidth = ref(960)
let observer: ResizeObserver | undefined
/** Ширина без отступов — сразу при появлении, не дожидаясь первого отчёта ResizeObserver */
function measure(element: HTMLElement) {
  const style = getComputedStyle(element)
  containerWidth.value = element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
}
watch(scroller, (element) => {
  observer?.disconnect()
  if (!element) return
  measure(element)
  observer = new ResizeObserver(() => measure(element))
  observer.observe(element)
})

const geometry = computed(() => (graph.value ? mapGeometry(graph.value, columnWidth(graph.value, containerWidth.value)) : null))

const r = STAGE_RADIUS
const markerId = useId()

/** Выбранный этап; не выбран — подробности текущего (или последнего) */
const selected = ref<StageKey | null>(null)
const shownKey = computed(() => selected.value ?? progress.value?.current ?? progress.value?.path.at(-1) ?? null)
const toggle = (key: StageKey) => (selected.value = selected.value === key ? null : key)

interface StageView {
  stage: Stage
  progress: StageProgress
  x: number
  y: number
  /** Финал, которым кончился маршрут: выдача, отказ, «закрыта» */
  finale: boolean
}

const stageViews = computed<StageView[]>(() => {
  const value = progress.value
  const geo = geometry.value
  if (!value || !geo || !graph.value) return []
  return graph.value.stages.flatMap((stage) => {
    const point = geo.points.get(stage.key)
    const state = value.stages.get(stage.key)
    return point && state ? [{ stage, progress: state, x: point.x, y: point.y, finale: value.finale === stage.key }] : []
  })
})
const shown = computed(() => stageViews.value.find((view) => view.stage.key === shownKey.value) ?? null)

const edgeViews = computed(() => {
  const traversed = progress.value?.traversed
  return (geometry.value?.edges ?? [])
    .map((edge) => ({
      key: `${edge.from}>${edge.to}`,
      d: roundedPath(edge.points),
      both: edge.both,
      done: Boolean(traversed?.has(`${edge.from}>${edge.to}`) || (edge.both && traversed?.has(`${edge.to}>${edge.from}`))),
    }))
    .sort((a, b) => Number(a.done) - Number(b.done))
})

const WAITING_LABEL: Record<WaitingFor, string> = { client: 'ждёт клиента', underwriter: 'у андеррайтера', service: 'ждёт сервис' }
const WAITING_WHOM: Record<WaitingFor, string> = { client: 'Клиента', underwriter: 'Андеррайтера', service: 'Ответа внешнего сервиса' }

const STATE_BADGE: Record<StageState, { label: string; tone: BadgeTone }> = {
  done: { label: 'Пройден', tone: 'success' },
  current: { label: 'Заявка здесь', tone: 'brand' },
  failed: { label: 'Ошибка', tone: 'brand' },
  stopped: { label: 'Процесс остановлен здесь', tone: 'neutral' },
  ahead: { label: 'Впереди', tone: 'neutral' },
  skipped: { label: 'Не понадобился', tone: 'neutral' },
}
const FINALE_BADGE: Record<string, { label: string; tone: BadgeTone }> = {
  disbursement: { label: 'Кредит выдан', tone: 'success' },
  // Заголовок этапа уже «Отказ» — бейдж говорит, что это конец маршрута
  rejected: { label: 'Итог маршрута', tone: 'brand' },
  closed: { label: 'Клиент не принял предложение', tone: 'neutral' },
}
/** У этапов до подачи — свои слова: предскоринга могло не быть, проверка учредителя может быть не пройдена */
const PRELUDE_BADGE: Partial<Record<StageState, { label: string; tone: BadgeTone }>> = {
  current: { label: 'Клиент сейчас здесь', tone: 'brand' },
  failed: { label: 'Не пройден', tone: 'brand' },
  skipped: { label: 'Не было', tone: 'neutral' },
}
const badgeOf = (view: StageView) =>
  (view.finale && FINALE_BADGE[view.stage.key]) ||
  (isPrelude(view.stage.key) && PRELUDE_BADGE[view.progress.state]) ||
  STATE_BADGE[view.progress.state]

/** Строка под точкой этапа: сколько занял, кого ждёт */
function statusLine(view: StageView): string {
  if (isPrelude(view.stage.key)) return preludeNote.value.get(view.stage.key) ?? ''
  const { state, waitingFor, durationMs } = view.progress
  if (state === 'current') return waitingFor ? WAITING_LABEL[waitingFor] : 'в работе'
  if (state === 'failed') return 'ошибка'
  if (state === 'stopped') return 'остановлен'
  if (state === 'done' && durationMs !== null) return formatDuration(durationMs)
  if (view.finale) return 'итог'
  return ''
}

type Look = 'done' | 'current' | 'failed' | 'stopped' | 'ahead' | 'skipped' | 'rejected' | 'closed'
function lookOf(view: StageView): Look {
  if (view.finale && view.stage.key === 'rejected') return 'rejected'
  if (view.finale && view.stage.key === 'closed') return 'closed'
  return view.progress.state
}
const CIRCLE_CLASS: Record<Look, string> = {
  done: 'fill-success stroke-success',
  current: 'fill-white stroke-brand',
  failed: 'fill-brand stroke-brand',
  stopped: 'fill-surface-strong stroke-ink-muted',
  ahead: 'fill-white stroke-ink-muted',
  skipped: 'fill-surface stroke-surface-strong',
  rejected: 'fill-brand-soft stroke-brand',
  closed: 'fill-surface-strong stroke-ink-muted',
}
const TITLE_CLASS: Record<Look, string> = {
  done: 'fill-ink',
  current: 'fill-ink',
  failed: 'fill-brand',
  stopped: 'fill-ink',
  ahead: 'fill-ink-secondary',
  skipped: 'fill-ink-muted',
  rejected: 'fill-brand',
  closed: 'fill-ink',
}
/** Подпись этапа не шире колонки: длинное имя чужого узла BPMN обрезаем, полное — во всплывающей подсказке */
const shortTitle = (title: string) => (title.length > 14 ? `${title.slice(0, 13)}…` : title)

// Красная точка: при первом показе — сразу на текущем этапе, дальше едет по каждому новому переходу
const dot = reactive({ x: 0, y: 0 })
const animating = ref(false)
const showDot = computed(() => Boolean(progress.value && (!progress.value.finished || animating.value)))
const reduceMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
let shownLength = 0
/** Этап, на котором точка остановилась, — от него считаем новые переходы, даже если начало пути поменялось */
let dotKey: StageKey | null = null
let queue: Point[][] = []
let frame = 0
let disposed = false

function placeDot(key: StageKey | undefined) {
  const point = key ? geometry.value?.points.get(key) : undefined
  if (point) Object.assign(dot, { x: point.x, y: point.y })
}

watch([progress, geometry], ([next, geo], [, previousGeo]) => {
  if (!next || !geo) return
  const path = next.path
  const resized = previousGeo && geo !== previousGeo
  // Где в новом пути этап, на котором стоит точка: начало пути может измениться (этапы до подачи
  // после подачи заявки), поэтому ищем по этапу, а не по номеру — последнее вхождение не дальше прежней
  // позиции со сдвигом на этапы до подачи (повторный заход на этап дальше по пути — уже другой переход)
  let from = -1
  if (dotKey) {
    for (let index = Math.min(path.length - 1, shownLength - 1 + props.prelude.length); index >= 0; index--) {
      if (path[index] === dotKey) {
        from = index
        break
      }
    }
  }
  if (shownLength === 0 || reduceMotion || from < 0) {
    queue = []
    cancelAnimationFrame(frame)
    animating.value = false
    placeDot(path.at(-1))
    if (shownLength === 0) void nextTick(scrollToCurrent)
    shownLength = path.length
    dotKey = path.at(-1) ?? null
    return
  }
  // Схема перерисовалась (сменилась ширина) без новых переходов — точку просто переставляем;
  // с новыми — она едет дальше по новой раскладке
  if (resized && !animating.value && from === path.length - 1) {
    placeDot(path.at(-1))
    shownLength = path.length
    return
  }
  for (let index = from + 1; index < path.length; index++) queue.push(hopLine(geo, path[index - 1]!, path[index]!))
  shownLength = path.length
  dotKey = path.at(-1) ?? null
  void animate()
})

async function animate() {
  if (animating.value) return
  animating.value = true
  while (queue.length && !disposed) {
    const line = queue.shift()!
    const total = lineLength(line)
    if (line.length < 2 || !total) continue
    const duration = Math.min(900, Math.max(320, total * 2.4))
    await new Promise<void>((resolve) => {
      const started = performance.now()
      const step = (time: number) => {
        const t = Math.min(1, (time - started) / duration)
        const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
        const [x, y] = pointAlong(line, eased * total)
        Object.assign(dot, { x, y })
        if (t < 1 && !disposed) frame = requestAnimationFrame(step)
        else resolve()
      }
      frame = requestAnimationFrame(step)
    })
  }
  animating.value = false
}

/** На телефоне схема шире экрана — сразу показываем место, где заявка сейчас */
function scrollToCurrent() {
  const element = scroller.value
  const key = progress.value?.current ?? progress.value?.path.at(-1)
  const point = key ? geometry.value?.points.get(key) : undefined
  if (element && point && element.scrollWidth > element.clientWidth) element.scrollLeft = point.x - element.clientWidth / 2
}

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

const PROCESS_STATUS: Record<string, string> = {
  completed: 'Маршрут завершён',
  failed: 'Процесс остановился с ошибкой',
  cancelled: 'Процесс отменён',
}

const STEP_KIND: Record<ProcessStepDto['kind'], string> = {
  immediate: 'сразу',
  async: 'внешний сервис',
  stoppable: 'ждёт человека',
}
const nodeName = (nodeId: string) => graph.value?.workflow.nodes.get(nodeId)?.name ?? nodeId
/** Один шаг с тем же названием, что у этапа («Отказ», «Скоринг»), ничего не добавляет: время уже показано выше */
const showSteps = computed(() => {
  const steps = shown.value?.progress.steps ?? []
  return steps.length > 1 || (steps.length === 1 && nodeName(steps[0]!.node_id) !== shown.value?.stage.title)
})
const stepDuration = (step: ProcessStepDto) =>
  formatDuration(new Date(step.finished_at ?? now.value).getTime() - new Date(step.started_at).getTime())
</script>

<template>
  <PanelCard
    title="Маршрут заявки"
    :description="description"
  >
    <template v-if="!process && graph" #actions>
      <span class="text-xs text-ink-secondary">Заявка ещё не подана — процесс начнётся с подачи</span>
    </template>
    <template v-else-if="process" #actions>
      <span v-if="error" class="text-xs font-medium text-warning">Нет связи — повторим через 10 секунд</span>
      <span v-else-if="progress?.finished" class="text-xs text-ink-secondary">
        {{ PROCESS_STATUS[process.status] }}<template v-if="process.finished_at"> · {{ formatDateTime(process.finished_at) }}</template>
      </span>
      <span v-else class="flex items-center gap-1.5 text-xs text-ink-secondary">
        <span class="live-dot size-2 rounded-full bg-success" aria-hidden="true" />
        В реальном времени
      </span>
    </template>

    <div v-if="loading && !graph" class="h-44 animate-pulse rounded-xl bg-surface-soft" aria-label="Загружаем маршрут" />
    <p v-else-if="missing && !graph" class="text-sm text-ink-secondary">
      Процесс по заявке ещё не запущен — схема появится, когда банк примет заявку в работу.
    </p>
    <div v-else-if="error && !graph" class="flex flex-wrap items-center gap-3 text-sm">
      <span class="text-ink-secondary">Не удалось загрузить маршрут: {{ error }}</span>
      <BaseButton size="s" variant="secondary" @click="tracking.refresh">Повторить</BaseButton>
    </div>

    <template v-else-if="geometry && progress">
      <div ref="scroller" class="-mx-5 overflow-x-auto px-5">
        <svg
          :width="geometry.width"
          :height="geometry.height"
          class="mx-auto block select-none"
          role="group"
          aria-label="Схема маршрута заявки по этапам"
        >
          <defs>
            <marker
              v-for="kind in ['done', 'idle']"
              :id="`${markerId}-${kind}`"
              :key="kind"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" :class="kind === 'done' ? 'fill-success' : 'fill-ink-muted'" />
            </marker>
          </defs>

          <path
            v-for="edge in edgeViews"
            :key="edge.key"
            :d="edge.d"
            fill="none"
            :class="edge.done ? 'stroke-success' : 'stroke-ink-muted'"
            :stroke-width="edge.done ? 2 : 1.5"
            :stroke-dasharray="edge.done ? undefined : '4 4'"
            :marker-end="edge.both ? undefined : `url(#${markerId}-${edge.done ? 'done' : 'idle'})`"
          />

          <g
            v-for="view in stageViews"
            :key="view.stage.key"
            :transform="`translate(${view.x} ${view.y})`"
            class="stage cursor-pointer outline-none"
            role="button"
            tabindex="0"
            :aria-label="`${view.stage.title}: ${badgeOf(view).label}`"
            :aria-pressed="shownKey === view.stage.key"
            @click="toggle(view.stage.key)"
            @keydown.enter.prevent="toggle(view.stage.key)"
            @keydown.space.prevent="toggle(view.stage.key)"
          >
            <title>{{ view.stage.subtitle || view.stage.title }}</title>
            <rect x="-42" :y="-r - 10" width="84" :height="r * 2 + 58" fill="transparent" />
            <circle
              class="focus-ring fill-none stroke-info"
              :class="shownKey === view.stage.key ? 'opacity-100' : 'opacity-0'"
              :r="r + 5"
              stroke-width="2"
            />
            <circle
              :r="r"
              :class="CIRCLE_CLASS[lookOf(view)]"
              :stroke-width="view.progress.state === 'current' ? 2.5 : 1.5"
              :stroke-dasharray="view.progress.state === 'ahead' ? '3 3' : undefined"
            />
            <path
              v-if="lookOf(view) === 'done'"
              d="M -5 0.5 L -1.5 4 L 5.5 -3.5"
              fill="none"
              class="stroke-white"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              v-else-if="lookOf(view) === 'failed' || lookOf(view) === 'rejected'"
              d="M -4.5 -4.5 L 4.5 4.5 M 4.5 -4.5 L -4.5 4.5"
              fill="none"
              :class="lookOf(view) === 'failed' ? 'stroke-white' : 'stroke-brand'"
              stroke-width="2.2"
              stroke-linecap="round"
            />
            <path
              v-else-if="lookOf(view) === 'closed' || lookOf(view) === 'stopped'"
              d="M -5 0 L 5 0"
              class="stroke-ink-secondary"
              stroke-width="2.2"
              stroke-linecap="round"
            />

            <g v-if="view.progress.visits > 1" :transform="`translate(${r - 2} ${-r + 2})`">
              <circle r="8.5" class="fill-ink stroke-white" stroke-width="1.5" />
              <text text-anchor="middle" dy="3.2" class="fill-white text-[9px] font-bold">×{{ view.progress.visits }}</text>
            </g>

            <text :y="r + 17" text-anchor="middle" class="text-xs font-semibold" :class="TITLE_CLASS[lookOf(view)]">
              {{ shortTitle(view.stage.title) }}
            </text>
            <text
              :y="r + 32"
              text-anchor="middle"
              class="text-[11px]"
              :class="view.progress.state === 'current' || view.progress.state === 'failed' ? 'fill-brand' : 'fill-ink-secondary'"
            >
              {{ statusLine(view) }}
            </text>
          </g>

          <g v-if="showDot" :transform="`translate(${dot.x} ${dot.y})`" class="pointer-events-none" aria-hidden="true">
            <circle class="pulse fill-brand" r="6" />
            <circle class="fill-brand" r="6" />
          </g>
        </svg>
      </div>

      <div class="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-ink-secondary">
        <span>Нажмите на этап, чтобы увидеть подробности</span>
        <span class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span class="flex items-center gap-1.5"><span class="size-2.5 rounded-full bg-success" aria-hidden="true" />пройден</span>
          <span class="flex items-center gap-1.5"><span class="size-2.5 rounded-full bg-brand" aria-hidden="true" />сейчас</span>
          <span class="flex items-center gap-1.5">
            <span class="size-2.5 rounded-full border border-dashed border-ink-muted" aria-hidden="true" />впереди
          </span>
        </span>
      </div>

      <section v-if="shown" class="mt-4 rounded-xl bg-surface-soft p-4" aria-live="polite">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-sm font-bold text-ink">{{ shown.stage.title }}</h3>
          <BaseBadge :tone="badgeOf(shown).tone">{{ badgeOf(shown).label }}</BaseBadge>
          <span v-if="shown.progress.visits > 1" class="text-xs text-ink-secondary">
            {{ shown.progress.visits }} {{ pluralize(shown.progress.visits, ['заход', 'захода', 'заходов']) }}
          </span>
        </div>
        <p v-if="shown.stage.subtitle && shown.stage.subtitle !== shown.stage.title" class="mt-0.5 text-xs text-ink-secondary">
          {{ shown.stage.subtitle }}
        </p>

        <dl v-if="shown.progress.enteredAt && !isPrelude(shown.stage.key)" class="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <dt class="text-xs text-ink-secondary">Начало</dt>
            <dd class="font-medium text-ink">{{ formatDateTime(shown.progress.enteredAt) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-ink-secondary">{{ shown.progress.leftAt ? 'Завершён' : 'Сейчас' }}</dt>
            <dd class="font-medium text-ink">
              {{ shown.progress.leftAt ? formatDateTime(shown.progress.leftAt) : process?.client_stage || 'идёт' }}
            </dd>
          </div>
          <div v-if="shown.progress.durationMs !== null">
            <dt class="text-xs text-ink-secondary">{{ shown.progress.leftAt ? 'Занял' : 'Идёт уже' }}</dt>
            <dd class="font-medium text-ink">{{ formatDuration(shown.progress.durationMs) }}</dd>
          </div>
          <div v-if="shown.progress.waitingFor">
            <dt class="text-xs text-ink-secondary">Ждём</dt>
            <dd class="font-medium text-ink">{{ WAITING_WHOM[shown.progress.waitingFor] }}</dd>
          </div>
        </dl>
        <p v-else-if="shown.progress.state === 'ahead' && !isPrelude(shown.stage.key)" class="mt-2 text-sm text-ink-secondary">
          Заявка сюда ещё не дошла.
        </p>
        <p v-else-if="shown.progress.state === 'skipped' && !shown.finale && !isPrelude(shown.stage.key)" class="mt-2 text-sm text-ink-secondary">
          На этой заявке этап не понадобился.
        </p>

        <p v-if="shown.progress.error" class="mt-3 rounded-lg bg-brand-soft p-2.5 text-sm text-brand">{{ shown.progress.error }}</p>

        <slot
          name="details"
          :stage="shown.stage.key"
          :state="shown.progress.state"
          :windows="shown.progress.windows"
        />

        <details v-if="showSteps" class="mt-3 text-sm">
          <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">
            Шаги процесса ({{ shown.progress.steps.length }})
          </summary>
          <ol class="mt-2 space-y-1.5">
            <li
              v-for="step in shown.progress.steps"
              :key="`${step.node_id}-${step.iteration}`"
              class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5"
            >
              <span class="text-ink">
                {{ nodeName(step.node_id) }}
                <span v-if="step.iteration > 1" class="text-xs text-ink-secondary">· повтор {{ step.iteration }}</span>
                <span class="text-xs text-ink-muted"> · {{ STEP_KIND[step.kind] ?? step.kind }}</span>
              </span>
              <span class="text-xs text-ink-secondary tabular-nums">
                {{ formatTime(step.started_at) }}–{{ step.finished_at ? formatTime(step.finished_at) : 'идёт' }} · {{ stepDuration(step) }}
              </span>
              <span v-if="step.error" class="basis-full text-xs text-brand">{{ step.error }}</span>
            </li>
          </ol>
        </details>
      </section>

      <slot name="footer" />
    </template>
  </PanelCard>
</template>

<style scoped>
.stage:focus-visible .focus-ring {
  opacity: 1;
}

.pulse {
  transform-box: fill-box;
  transform-origin: center;
  animation: pulse 1.6s ease-out infinite;
}

.live-dot {
  animation: live 2s ease-in-out infinite;
}

@keyframes pulse {
  from {
    transform: scale(1);
    opacity: 0.5;
  }
  to {
    transform: scale(3);
    opacity: 0;
  }
}

@keyframes live {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pulse,
  .live-dot {
    animation: none;
  }
}
</style>
