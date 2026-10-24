import type { ProcessProgress, StageProgress } from './progress'
import type { Stage, StageGraph, StageKey, StagePlacement } from './stages'

/**
 * Этапы до подачи заявки — как на общей схеме банка: согласия, предскоринг; у стартапа — проверка
 * учредителя и проектная оценка. Процесс заявки их не знает (он начинается с подачи), поэтому их
 * собирает тот, кто встраивает схему, из данных компании, а здесь они встают в начало маршрута.
 */
export interface PreludeStage {
  key: `pre:${string}`
  title: string
  subtitle: string
  /** done — пройден, current — клиент сейчас здесь, failed — не пройден, skipped — не делали / не понадобился, ahead — впереди */
  state: 'done' | 'current' | 'failed' | 'skipped' | 'ahead'
  /** Когда прошёл: для подробностей и раскладки событий */
  at: string | null
  /** Строка под точкой: «до 4 млн ₽», «пройдена» */
  note: string
}

/** Маршрут с этапами до подачи в начале основной линии: они идут цепочкой и ведут в «Подачу» */
export function withPrelude(graph: StageGraph, prelude: readonly PreludeStage[]): StageGraph {
  if (!prelude.length) return graph
  const shift = prelude.length
  const stages: Stage[] = [
    ...prelude.map((item) => ({ key: item.key, title: item.title, subtitle: item.subtitle, nodeIds: [], terminal: false })),
    ...graph.stages,
  ]
  const keys = [...prelude.map((item) => item.key), graph.start]
  const edges = [...keys.slice(1).map((to, index) => ({ from: keys[index]!, to })), ...graph.edges]
  const placement = new Map<StageKey, StagePlacement>(prelude.map((item, col) => [item.key, { col, row: 0 }]))
  for (const [key, place] of graph.placement) placement.set(key, { ...place, col: place.col + shift })
  return {
    ...graph,
    stages,
    edges,
    placement,
    mainLine: [...prelude.map((item) => item.key), ...graph.mainLine],
  }
}

/** Ход по маршруту, когда процесса ещё нет (черновик): все этапы маршрута впереди */
export function emptyProgress(graph: StageGraph): ProcessProgress {
  const stages = new Map<StageKey, StageProgress>()
  for (const stage of graph.stages) stages.set(stage.key, idle('ahead'))
  return { path: [], current: null, finale: null, finished: false, stages, traversed: new Set() }
}

/**
 * Ход с этапами до подачи: пройденные (и текущий у черновика) встают в начало пути, красная точка
 * у черновика — на текущем этапе до подачи.
 */
export function withPreludeProgress(progress: ProcessProgress, prelude: readonly PreludeStage[], start: StageKey): ProcessProgress {
  if (!prelude.length) return progress
  const before = prelude.filter((item) => item.state === 'done' || item.state === 'current' || item.state === 'failed').map((item) => item.key)
  const path: StageKey[] = [...before, ...progress.path]
  const current = progress.current ?? (progress.path.length ? null : (prelude.find((item) => item.state === 'current')?.key ?? null))
  const stages = new Map(progress.stages)
  for (const item of prelude) {
    stages.set(item.key, {
      ...idle(item.state === 'current' ? 'current' : item.state === 'failed' ? 'failed' : item.state),
      visits: item.state === 'skipped' || item.state === 'ahead' ? 0 : 1,
      enteredAt: item.at,
      leftAt: item.state === 'current' ? null : item.at,
      waitingFor: item.state === 'current' ? 'client' : null,
    })
  }
  // Линии до подачи — по цепочке, включая пропущенные этапы: заявку подали — пройдена вся цепочка,
  // черновик — до этапа, где клиент сейчас
  const traversed = new Set(progress.traversed)
  const chain: StageKey[] = [...prelude.map((item) => item.key), start]
  const reached = progress.path.length ? chain.length - 1 : current ? chain.indexOf(current) : -1
  for (let index = 1; index <= reached; index++) traversed.add(`${chain[index - 1]}>${chain[index]}`)
  return { ...progress, path, current, stages, traversed }
}

function idle(state: StageProgress['state']): StageProgress {
  return { state, visits: 0, steps: [], enteredAt: null, leftAt: null, durationMs: null, waitingFor: null, error: null, windows: [] }
}
