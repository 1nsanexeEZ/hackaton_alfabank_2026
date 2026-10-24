import { isEndEvent, isGateway, isStartEvent, type BpmnNode, type Workflow } from './bpmn'

/**
 * Упрощённая схема маршрута по этапам. Узлы BPMN собираем в этапы, понятные сотруднику
 * («Проверить полноту» и шлюз «Заявка полная?» — один этап «Полнота»), шлюзы прозрачны:
 * переход идёт сразу между этапами. Id узлов одинаковы во всех маршрутах бэкенда
 * (backend/src/modules/process/workflows/*.bpmn); узел, которого нет в справочнике, — отдельный этап.
 */

export type KnownStage =
  | 'submitted'
  | 'completeness'
  | 'info_request'
  | 'enrichment'
  | 'stop_factors'
  | 'collateral'
  | 'scoring'
  | 'decision'
  | 'underwriter'
  | 'offer'
  | 'signing'
  | 'disbursement'
  | 'rejected'
  | 'closed'

export type StageKey = KnownStage | `node:${string}`

export const STAGE_TITLE: Record<KnownStage, string> = {
  submitted: 'Подача',
  completeness: 'Полнота',
  info_request: 'Дозапрос',
  enrichment: 'Данные',
  stop_factors: 'Стоп-факторы',
  collateral: 'Залог',
  scoring: 'Скоринг',
  decision: 'Решение',
  underwriter: 'Андеррайтер',
  offer: 'Оффер',
  signing: 'Подписание',
  disbursement: 'Выдача',
  rejected: 'Отказ',
  closed: 'Закрыта',
}

const STAGE_OF_NODE: Record<string, KnownStage> = {
  start: 'submitted',
  start_review: 'submitted',
  check_completeness: 'completeness',
  request_info: 'info_request',
  wait_client_info: 'info_request',
  fetch_enrichment: 'enrichment',
  check_stop_factors: 'stop_factors',
  assess_collateral: 'collateral',
  calculate_score: 'scoring',
  make_decision: 'decision',
  underwriter_review: 'underwriter',
  record_manual_decision: 'underwriter',
  present_offer: 'offer',
  wait_offer_answer: 'offer',
  wait_signature: 'signing',
  disburse: 'disbursement',
  end_disbursed: 'disbursement',
  reject: 'rejected',
  end_rejected: 'rejected',
  end_closed: 'closed',
}

/**
 * Куда этап ведёт на самом деле, если шлюзы дают больше. Сработавший стоп-фактор (маршруты *_v2) идёт
 * через «Стоп-фактор?» на общий шлюз исхода, но оттуда — только отказ или, у ИП без согласия на
 * авторешение, андеррайтер: предложения и дозапроса после стоп-фактора не бывает.
 */
const STAGE_EXITS: Partial<Record<KnownStage, readonly StageKey[]>> = {
  stop_factors: ['collateral', 'scoring', 'rejected', 'underwriter'],
}

export interface Stage {
  key: StageKey
  title: string
  /** Что делается на этапе — название задачи BPMN: «Проверка андеррайтером», у стартапа — «Проектная оценка» */
  subtitle: string
  nodeIds: readonly string[]
  /** Финал маршрута: выдача, отказ, клиент не принял предложение */
  terminal: boolean
}

export interface StageEdge {
  from: StageKey
  to: StageKey
}

/** Место этапа: col — колонка основной линии (у ответвлений дробная, между колонками), row — над (-1), на (0) или под (1) линией */
export interface StagePlacement {
  col: number
  row: -1 | 0 | 1
}

export interface StageGraph {
  workflow: Workflow
  stages: readonly Stage[]
  edges: readonly StageEdge[]
  start: StageKey
  /** Этапы основной линии — самый длинный путь от подачи до финала */
  mainLine: readonly StageKey[]
  placement: ReadonlyMap<StageKey, StagePlacement>
  /** Этап узла BPMN; шлюз и чужой узел — null */
  stageOf(nodeId: string): StageKey | null
  /** Финалы, в которые процесс попадает из узла сразу, через одни шлюзы: после «Ответ клиента» — «Закрыта» */
  endsAfter(nodeId: string): StageKey[]
}

const keyOfNode = (node: BpmnNode): StageKey => STAGE_OF_NODE[node.id] ?? (isStartEvent(node) ? 'submitted' : `node:${node.id}`)
const titleOf = (key: StageKey, node: BpmnNode): string => (key.startsWith('node:') ? node.name : STAGE_TITLE[key as KnownStage])

export function buildStageGraph(workflow: Workflow): StageGraph {
  const stageOfNode = new Map<string, StageKey>()
  const grouped = new Map<StageKey, BpmnNode[]>()
  for (const node of workflow.nodes.values()) {
    if (isGateway(node)) continue
    const key = keyOfNode(node)
    stageOfNode.set(node.id, key)
    grouped.set(key, [...(grouped.get(key) ?? []), node])
  }

  const outgoing = new Map<string, string[]>()
  for (const flow of workflow.flows) outgoing.set(flow.source, [...(outgoing.get(flow.source) ?? []), flow.target])

  /** Ближайшие узлы-не-шлюзы после узла: шлюзы проходим насквозь */
  function nextNodes(nodeId: string): BpmnNode[] {
    const found: BpmnNode[] = []
    const seen = new Set<string>()
    const walk = (id: string) => {
      for (const target of outgoing.get(id) ?? []) {
        if (seen.has(target)) continue
        seen.add(target)
        const node = workflow.nodes.get(target)
        if (!node) continue
        if (isGateway(node)) walk(target)
        else found.push(node)
      }
    }
    walk(nodeId)
    return found
  }

  const edgeKeys = new Set<string>()
  const edges: StageEdge[] = []
  for (const [nodeId, from] of stageOfNode) {
    for (const next of nextNodes(nodeId)) {
      const to = stageOfNode.get(next.id)
      if (!to || to === from || edgeKeys.has(`${from}>${to}`)) continue
      const exits = STAGE_EXITS[from as KnownStage]
      if (exits && !exits.includes(to)) continue
      edgeKeys.add(`${from}>${to}`)
      edges.push({ from, to })
    }
  }

  const startNode = [...workflow.nodes.values()].find(isStartEvent)
  const start = (startNode && stageOfNode.get(startNode.id)) ?? 'submitted'

  const stages: Stage[] = [...grouped].map(([key, nodes]) => {
    const tasks = nodes.filter((node) => !isStartEvent(node) && !isEndEvent(node))
    const main = tasks.find((node) => node.type === 'userTask') ?? tasks[0] ?? nodes[0]!
    return {
      key,
      title: titleOf(key, main),
      subtitle: tasks.length ? main.name : '',
      nodeIds: nodes.map((node) => node.id),
      terminal: nodes.some(isEndEvent) && !edges.some((edge) => edge.from === key),
    }
  })

  const { mainLine, placement } = layout(stages, edges, start)

  return {
    workflow,
    stages,
    edges,
    start,
    mainLine,
    placement,
    stageOf: (nodeId) => stageOfNode.get(nodeId) ?? null,
    endsAfter: (nodeId) =>
      nextNodes(nodeId)
        .filter(isEndEvent)
        .map((node) => stageOfNode.get(node.id)!)
        .filter((key, index, all) => all.indexOf(key) === index),
  }
}

/**
 * Раскладка: основная линия — самый длинный путь без циклов от подачи до финала (при равенстве — тот,
 * что кончается выдачей). Остальные этапы — ответвления: возвращающиеся назад (дозапрос) — над линией,
 * остальные (отказ, «закрыта») — под ней, между колонками этапов, из которых в них попадают.
 */
function layout(stages: readonly Stage[], edges: readonly StageEdge[], start: StageKey) {
  const adjacency = new Map<StageKey, StageKey[]>()
  for (const edge of edges) adjacency.set(edge.from, [...(adjacency.get(edge.from) ?? []), edge.to])

  // Обратные рёбра (к этапу, который ещё на стеке обхода) выкидываем — остаётся граф без циклов
  const forward = new Map<StageKey, StageKey[]>()
  const status = new Map<StageKey, 'open' | 'done'>()
  const visit = (key: StageKey) => {
    status.set(key, 'open')
    for (const next of adjacency.get(key) ?? []) {
      if (status.get(next) === 'open') continue
      forward.set(key, [...(forward.get(key) ?? []), next])
      if (!status.has(next)) visit(next)
    }
    status.set(key, 'done')
  }
  visit(start)

  const longest = new Map<StageKey, StageKey[]>()
  const pathFrom = (key: StageKey): StageKey[] => {
    const known = longest.get(key)
    if (known) return known
    let best: StageKey[] = []
    for (const next of forward.get(key) ?? []) {
      const candidate = pathFrom(next)
      const better =
        candidate.length > best.length || (candidate.length === best.length && candidate.at(-1) === 'disbursement')
      if (better) best = candidate
    }
    const path = [key, ...best]
    longest.set(key, path)
    return path
  }
  const mainLine = pathFrom(start)

  const placement = new Map<StageKey, StagePlacement>()
  mainLine.forEach((key, col) => placement.set(key, { col, row: 0 }))

  const colOf = (key: StageKey) => (placement.get(key)?.row === 0 ? placement.get(key)!.col : null)
  const branches = stages
    .filter((stage) => !placement.has(stage.key))
    .map((stage) => {
      const from = edges.filter((edge) => edge.to === stage.key).map((edge) => colOf(edge.from))
      const to = edges.filter((edge) => edge.from === stage.key).map((edge) => colOf(edge.to))
      const preds = from.filter((col): col is number => col !== null)
      const succs = to.filter((col): col is number => col !== null)
      const loopsBack = succs.length > 0 && succs.some((col) => col <= Math.max(...preds, -1))
      let col: number
      if (loopsBack) col = Math.min(...preds, ...succs) + 0.5
      else if (preds.length) col = Math.max(...preds) + 0.5
      else if (succs.length) col = Math.min(...succs) - 0.5
      else col = mainLine.length
      return { key: stage.key, row: (loopsBack ? -1 : 1) as -1 | 1, col }
    })
    .sort((a, b) => a.col - b.col)

  // Ответвления одного ряда не налезают друг на друга: не ближе колонки
  for (const row of [-1, 1] as const) {
    let previous = -Infinity
    for (const branch of branches.filter((item) => item.row === row)) {
      const col = Math.max(branch.col, previous + 1)
      placement.set(branch.key, { col, row })
      previous = col
    }
  }

  return { mainLine, placement }
}
