import { computed, inject, provide, reactive, ref, shallowRef, watch, type InjectionKey } from 'vue'

import {
  backofficeApi,
  type ApplicationStatusCode,
  type MetricsDto,
  type QueuePageDto,
  type StaffApplicationDto,
  type UnderwriterCardDto,
} from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Период метрик по дням: последние 7, 30 или 90 дней */
export type Period = '7' | '30' | '90'

/** Сколько заявок разбираем (страницы по 100) и сколько последних поданных оцениваем по карточкам */
const PAGE = 100
const MAX_PAGES = 3
const SCORED_LIMIT = 30
const PARALLEL = 6

const isoDay = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`

function daysAgo(days: number) {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date
}

export const amountOf = (item: StaffApplicationDto) => (item.amount ? Number(item.amount) : 0)
export const isSubmitted = (status: ApplicationStatusCode) => status !== 'draft'

/**
 * Данные панели заявок. Сводной ручки нет, поэтому складываем из того, что отдаёт бэкенд:
 * - заявки — GET /applications (все статусы, до 300 последних): воронка, статусы, продукты, суммы, лента;
 * - метрики — GET /bff/backoffice/metrics за период: поток по дням, автоматика и специалист, время решения;
 * - очередь специалиста — GET /bff/backoffice/queue (открытые задачи): сколько ждут, просрочка по SLA;
 * - карточки последних поданных — GET /bff/backoffice/applications/{id}: грейды скоринга. Их грузим, только
 *   когда модуль скоринга на панели виден: это до 30 запросов.
 */
export function useBoardData() {
  const period = ref<Period>('30')

  const applications = shallowRef<StaffApplicationDto[]>([])
  const applicationsLoading = ref(true)
  const applicationsError = ref<string | null>(null)

  async function loadApplications() {
    applicationsLoading.value = true
    applicationsError.value = null
    try {
      const loaded: StaffApplicationDto[] = []
      for (let page = 0; page < MAX_PAGES; page++) {
        const batch = await backofficeApi.applications({ limit: PAGE, offset: page * PAGE })
        loaded.push(...batch)
        if (batch.length < PAGE) break
      }
      applications.value = loaded
    } catch (caught) {
      applicationsError.value = errorMessage(caught)
    } finally {
      applicationsLoading.value = false
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

  const cards = shallowRef<UnderwriterCardDto[]>([])
  const cardsLoading = ref(false)
  let cardsRequested = false

  /** Карточки для скоринга — по первому запросу модуля, порциями по 6 */
  async function loadCards() {
    if (cardsRequested) return
    cardsRequested = true
    cardsLoading.value = true
    try {
      const submitted = applications.value.filter((item) => isSubmitted(item.status)).slice(0, SCORED_LIMIT)
      const loaded: UnderwriterCardDto[] = []
      for (let index = 0; index < submitted.length; index += PARALLEL) {
        const batch = await Promise.all(submitted.slice(index, index + PARALLEL).map((item) => backofficeApi.card(item.id).catch(() => null)))
        loaded.push(...batch.filter((card): card is UnderwriterCardDto => card !== null))
        cards.value = [...loaded]
      }
    } finally {
      cardsLoading.value = false
    }
  }

  /** Названия компаний — по одной загрузке на компанию */
  const companies = reactive<Record<string, { name: string; inn: string } | null>>({})
  function loadCompanies(ids: string[]) {
    for (const id of new Set(ids)) {
      if (id in companies) continue
      companies[id] = null
      backofficeApi
        .organization(id)
        .then((company) => (companies[id] = { name: company.name, inn: company.inn }))
        .catch(() => undefined)
    }
  }

  function reload() {
    cardsRequested = false
    cards.value = []
    void loadApplications()
    void loadMetrics()
    void loadQueue()
  }

  void loadApplications()
  void loadMetrics()
  void loadQueue()

  return {
    period,
    days,
    applications,
    applicationsLoading,
    applicationsError,
    metrics,
    metricsLoading,
    metricsError,
    queue,
    queueLoading,
    queueError,
    cards,
    cardsLoading,
    loadCards,
    companies,
    loadCompanies,
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
