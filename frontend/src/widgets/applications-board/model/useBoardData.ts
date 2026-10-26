import { computed, inject, provide, ref, shallowRef, watch, type InjectionKey } from 'vue'

import { backofficeApi, type ApplicationsOverviewDto, type MetricsDto, type QueuePageDto, type ScoringOverviewDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Период метрик по дням: последние 7, 30 или 90 дней */
export type Period = '7' | '30' | '90'

/** Сколько последних изменённых заявок показывает лента */
const LATEST = 6
/** По скольким последним поданным заявкам модуль скоринга считает средний балл */
const SCORED_LIMIT = 30

const isoDay = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

function daysAgo(days: number) {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date
}

/** Сумма строкой из сводки — числом; пустая и кривая — ноль */
export const toAmount = (value: string | null | undefined) => (value ? Number(value) || 0 : 0)

/**
 * Данные панели заявок — по одной ручке на источник:
 * - сводка заявок — GET /bff/backoffice/applications-overview: воронка, статусы, продукты, суммы и лента
 *   последних заявок по ВСЕМ заявкам, считает база;
 * - метрики — GET /bff/backoffice/metrics за период: поток по дням, автоматика и специалист, время решения;
 * - очередь специалиста — GET /bff/backoffice/queue (открытые задачи): сколько ждут, просрочка по SLA;
 * - сводка скоринга — GET /bff/backoffice/scoring-overview: грейды. Её грузим, только когда модуль
 *   скоринга на панели виден.
 */
export function useBoardData() {
  const period = ref<Period>('30')

  const overview = shallowRef<ApplicationsOverviewDto | null>(null)
  const overviewLoading = ref(true)
  const overviewError = ref<string | null>(null)

  async function loadOverview() {
    overviewLoading.value = true
    overviewError.value = null
    try {
      overview.value = await backofficeApi.applicationsOverview(LATEST)
    } catch (caught) {
      overviewError.value = errorMessage(caught)
    } finally {
      overviewLoading.value = false
    }
  }

  const metrics = shallowRef<MetricsDto | null>(null)
  const metricsLoading = ref(true)
  const metricsError = ref<string | null>(null)

  async function loadMetrics() {
    metricsLoading.value = true
    metricsError.value = null
    try {
      metrics.value = await backofficeApi.metrics({ dateFrom: isoDay(daysAgo(Number(period.value) - 1)), dateTo: isoDay(new Date()) })
    } catch (caught) {
      metricsError.value = errorMessage(caught)
    } finally {
      metricsLoading.value = false
    }
  }
  watch(period, () => void loadMetrics())

  const queue = shallowRef<QueuePageDto | null>(null)
  const queueLoading = ref(true)
  const queueError = ref<string | null>(null)

  async function loadQueue() {
    queueLoading.value = true
    queueError.value = null
    try {
      queue.value = await backofficeApi.queue({ status: 'open', limit: 100 })
    } catch (caught) {
      queueError.value = errorMessage(caught)
    } finally {
      queueLoading.value = false
    }
  }

  /** Дни периода по порядку — у метрик нет строк за дни без заявок, а график без пропусков */
  const days = computed(() => {
    const count = Number(period.value)
    return Array.from({ length: count }, (_, index) => isoDay(daysAgo(count - 1 - index)))
  })

  const scoring = shallowRef<ScoringOverviewDto | null>(null)
  const scoringLoading = ref(false)
  let scoringRequested = false

  /** Сводка скоринга — по первому запросу модуля */
  async function loadScoring() {
    if (scoringRequested) return
    scoringRequested = true
    scoringLoading.value = true
    try {
      scoring.value = await backofficeApi.scoringOverview(SCORED_LIMIT)
    } catch {
      scoringRequested = false
    } finally {
      scoringLoading.value = false
    }
  }

  function reload() {
    const hadScoring = scoringRequested
    scoringRequested = false
    void loadOverview()
    void loadMetrics()
    void loadQueue()
    if (hadScoring) void loadScoring()
  }

  void loadOverview()
  void loadMetrics()
  void loadQueue()

  return {
    period,
    days,
    overview,
    overviewLoading,
    overviewError,
    metrics,
    metricsLoading,
    metricsError,
    queue,
    queueLoading,
    queueError,
    scoring,
    scoringLoading,
    loadScoring,
    reload,
  }
}

export type BoardData = ReturnType<typeof useBoardData>

const BOARD_KEY: InjectionKey<BoardData> = Symbol('applications-board')

/** Панель отдаёт данные модулям через provide: модуль не знает, откуда они и кто ещё их читает */
export function provideBoard(data: BoardData) {
  provide(BOARD_KEY, data)
}

export function useBoard(): BoardData {
  const data = inject(BOARD_KEY)
  if (!data) throw new Error('Модуль панели заявок вне ApplicationsBoard')
  return data
}
