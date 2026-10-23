import { onScopeDispose, ref, shallowRef } from 'vue'

import { ApiError, backofficeApi, type ProcessDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

import { parseWorkflow } from './bpmn'
import { buildStageGraph, type StageGraph } from './stages'

/**
 * Процесс заявки в реальном времени. Поток SSE сотрудника шлёт события заявки, а не шаги процесса,
 * поэтому опрашиваем GET /processes/{id}: пока процесс идёт — раз в 1,5 с, пока ждёт человека или
 * сервис — раз в 5 с, после финала — перестаём. На скрытой вкладке опрос на паузе.
 */

const RUNNING_INTERVAL = 1500
const WAITING_INTERVAL = 5000
const RETRY_INTERVAL = 10_000

// Схема маршрута одна на все заявки этого маршрута — грузим один раз за сессию
const graphs = new Map<string, Promise<StageGraph>>()

function loadGraph(code: string): Promise<StageGraph> {
  let graph = graphs.get(code)
  if (!graph) {
    graph = backofficeApi.workflowDiagram(code).then((xml) => buildStageGraph(parseWorkflow(xml)))
    graph.catch(() => graphs.delete(code))
    graphs.set(code, graph)
  }
  return graph
}

export interface ProcessTrackingOptions {
  /** Процесс продвинулся — например, перечитать карточку, чтобы подробности этапов были свежими */
  onAdvance?: (process: ProcessDto) => void
}

export function useProcessTracking(applicationId: () => string, options: ProcessTrackingOptions = {}) {
  const process = shallowRef<ProcessDto | null>(null)
  const graph = shallowRef<StageGraph | null>(null)
  const loading = ref(true)
  /** Процесса по заявке ещё нет: черновик или заявку только подают */
  const missing = ref(false)
  const error = ref<string | null>(null)
  /** Когда получили процесс — от этого считаем, сколько идёт текущий шаг */
  const now = ref(Date.now())

  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let inFlight = false
  let fingerprint = ''

  function schedule(delay: number | null) {
    clearTimeout(timer)
    if (delay !== null && !disposed) timer = setTimeout(() => void poll(), delay)
  }

  async function poll() {
    clearTimeout(timer)
    // Первую загрузку делаем и в фоновой вкладке; дальше на скрытой вкладке ждём, пока её откроют
    if (disposed || inFlight || (document.hidden && process.value)) return
    inFlight = true
    try {
      const next = await backofficeApi.process(applicationId())
      if (!graph.value || graph.value.workflow.code !== next.workflow_code) graph.value = await loadGraph(next.workflow_code)
      if (disposed) return
      const print = `${next.status}|${next.current_node_id}|${next.steps.length}|${next.steps.at(-1)?.finished_at ?? ''}`
      const advanced = fingerprint !== '' && print !== fingerprint
      fingerprint = print
      process.value = next
      now.value = Date.now()
      missing.value = false
      error.value = null
      if (advanced) options.onAdvance?.(next)
      schedule(next.status === 'running' ? RUNNING_INTERVAL : next.status === 'waiting' ? WAITING_INTERVAL : null)
    } catch (caught) {
      if (disposed) return
      if (caught instanceof ApiError && caught.status === 404) missing.value = true
      else error.value = errorMessage(caught)
      schedule(RETRY_INTERVAL)
    } finally {
      inFlight = false
      loading.value = false
    }
  }

  const finished = () => ['completed', 'failed', 'cancelled'].includes(process.value?.status ?? '')
  const onVisibility = () => {
    if (!document.hidden && !finished()) void poll()
  }
  document.addEventListener('visibilitychange', onVisibility)
  onScopeDispose(() => {
    disposed = true
    clearTimeout(timer)
    document.removeEventListener('visibilitychange', onVisibility)
  })

  void poll()

  return {
    process,
    graph,
    loading,
    missing,
    error,
    now,
    /** Опросить сейчас — после решения андеррайтера процесс двинется раньше следующего опроса */
    refresh: () => poll(),
  }
}
