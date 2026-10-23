import type { ProcessDto, ProcessStepDto } from '@/shared/api'

import type { StageGraph, StageKey } from './stages'

/**
 * Где заявка на схеме по этапам. Путь строим по шагам процесса (они по времени и с повторами),
 * а не по visited_node_ids — там узлы без повторов, и второй заход на этап потерялся бы.
 */

/** done — пройден, current — заявка здесь, failed — шаг упал, stopped — процесс отменён здесь,
 *  ahead — может ещё быть, skipped — не понадобился (заявка ушла дальше или маршрут завершён) */
export type StageState = 'done' | 'current' | 'failed' | 'stopped' | 'ahead' | 'skipped'

/** Кого ждёт текущий этап: клиента, андеррайтера или ответа внешнего сервиса */
export type WaitingFor = 'client' | 'underwriter' | 'service'

/** Заход на этап: с начала его первого шага до начала следующего этапа; null — с самого начала / до сих пор */
export interface StageWindow {
  from: string | null
  to: string | null
}

export interface StageProgress {
  state: StageState
  /** Сколько раз заявка заходила на этап: дозапрос и повторная проверка полноты — 2 */
  visits: number
  steps: readonly ProcessStepDto[]
  enteredAt: string | null
  /** Когда этап закончился; null — ещё идёт или не начинался */
  leftAt: string | null
  /** Время на этапе, мс: сумма шагов, у идущего шага — до сейчас */
  durationMs: number | null
  waitingFor: WaitingFor | null
  error: string | null
  /** Заходы на этап — по ним события карточки раскладываются по этапам, каждое ровно в один */
  windows: readonly StageWindow[]
}

export interface ProcessProgress {
  /** Этапы в порядке прохождения, с повторами: подача → полнота → дозапрос → полнота → … */
  path: readonly StageKey[]
  /** Этап, на котором заявка сейчас; у завершённого процесса — null */
  current: StageKey | null
  /** Чем кончился маршрут: выдача, отказ, «закрыта»; null — ещё идёт */
  finale: StageKey | null
  finished: boolean
  stages: ReadonlyMap<StageKey, StageProgress>
  /** Пройденные переходы `from>to` — их линии на схеме сплошные */
  traversed: ReadonlySet<string>
}

const FINISHED = new Set(['completed', 'failed', 'cancelled'])

export function processProgress(graph: StageGraph, process: ProcessDto, now = Date.now()): ProcessProgress {
  const finished = FINISHED.has(process.status)

  const path: StageKey[] = [graph.start]
  for (const step of process.steps) {
    const key = graph.stageOf(step.node_id)
    if (key && path.at(-1) !== key) path.push(key)
  }

  const currentNode = process.current_node_id
  let current: StageKey | null = null
  if (!finished) {
    current = (currentNode && graph.stageOf(currentNode)) || path.at(-1) || null
    if (current && path.at(-1) !== current) path.push(current)
  }

  // Конечные события шагов не дают: «Закрыта» видно только по схеме — куда ведут шлюзы из последнего узла
  let finale: StageKey | null = null
  if (process.status === 'completed') {
    const last = path.at(-1)!
    const lastNode = process.steps.at(-1)?.node_id
    if (graph.stages.find((stage) => stage.key === last)?.terminal) finale = last
    else if (lastNode) {
      const ends = graph.endsAfter(lastNode)
      if (ends.length === 1) {
        finale = ends[0]!
        path.push(finale)
      }
    }
  }

  // Событие относим к этапу, который начался последним до него: события пишутся чуть позже шагов
  const windows = new Map<StageKey, StageWindow[]>()
  let open = null as { key: StageKey; window: StageWindow } | null
  for (const step of process.steps) {
    const key = graph.stageOf(step.node_id)
    if (!key || open?.key === key) continue
    if (open) open.window.to = step.started_at
    const window: StageWindow = { from: open ? step.started_at : null, to: null }
    windows.set(key, [...(windows.get(key) ?? []), window])
    open = { key, window }
  }
  if (finale && open && open.key !== finale) {
    const from = process.steps.at(-1)?.finished_at ?? process.finished_at
    open.window.to = from
    windows.set(finale, [{ from, to: null }])
  }

  const traversed = new Set<string>()
  for (let index = 1; index < path.length; index++) traversed.add(`${path[index - 1]}>${path[index]}`)

  const reached = path.at(-1)!
  const reachedCol = graph.placement.get(reached)?.col ?? 0
  const stages = new Map<StageKey, StageProgress>()
  for (const stage of graph.stages) {
    const steps = process.steps.filter((step) => graph.stageOf(step.node_id) === stage.key)
    const visits = path.filter((key) => key === stage.key).length
    const place = graph.placement.get(stage.key)

    let state: StageState
    if (stage.key === current) state = 'current'
    else if (finished && stage.key === reached && process.status === 'failed') state = 'failed'
    else if (finished && stage.key === reached && process.status === 'cancelled') state = 'stopped'
    else if (visits) state = 'done'
    else if (finished || (place?.row === 0 && place.col < reachedCol)) state = 'skipped'
    else state = 'ahead'

    const running = steps.filter((step) => !step.finished_at)
    const durationMs = steps.length
      ? steps.reduce((sum, step) => sum + (new Date(step.finished_at ?? now).getTime() - new Date(step.started_at).getTime()), 0)
      : null

    let waitingFor: WaitingFor | null = null
    if (state === 'current') {
      const groups = (currentNode && graph.workflow.nodes.get(currentNode)?.candidateGroups) || ''
      if (groups.includes('client')) waitingFor = 'client'
      else if (groups.includes('underwriter')) waitingFor = 'underwriter'
      else if (running.some((step) => step.kind === 'async')) waitingFor = 'service'
    }

    stages.set(stage.key, {
      state,
      visits,
      steps,
      enteredAt: steps[0]?.started_at ?? null,
      leftAt: steps.length && !running.length ? (steps.at(-1)!.finished_at ?? null) : null,
      durationMs,
      waitingFor,
      error: [...steps].reverse().find((step) => step.error)?.error ?? null,
      windows: windows.get(stage.key) ?? [],
    })
  }

  return { path, current, finale, finished, stages, traversed }
}
