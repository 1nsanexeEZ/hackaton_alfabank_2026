import type { StageGraph, StageKey } from './stages'

/**
 * Координаты схемы по этапам в пикселях: точки этапов и линии переходов. Подписи — под точками,
 * поэтому линии к ответвлениям идут по просветам между колонками, а пропуск этапа (авторешение
 * мимо андеррайтера) — дугой над линией.
 */

export type Point = readonly [number, number]

export interface StagePoint {
  x: number
  y: number
  row: -1 | 0 | 1
}

export interface EdgeLine {
  from: StageKey
  to: StageKey
  /** Ломаная от края точки до края точки; углы скругляет roundedPath */
  points: readonly Point[]
  /** Переход есть в обе стороны (полнота ⇄ дозапрос) — одна линия без стрелки */
  both: boolean
}

export interface MapGeometry {
  width: number
  height: number
  points: ReadonlyMap<StageKey, StagePoint>
  edges: readonly EdgeLine[]
}

export const STAGE_RADIUS = 14
const PAD_X = 44
/** Высота дуги пропуска над линией и сдвиг ряда ответвлений */
const SKIP_HEIGHT = 30
const ROW_GAP = 100
/** Над точками основной линии — место для дуг; под точками — для двух строк подписи */
const TOP_SPACE = 48
const LABEL_SPACE = 58

export const COLUMN_MIN = 78
export const COLUMN_MAX = 132

/** Ширина колонки под ширину контейнера: схема во всю панель, на телефоне — прокрутка */
export function columnWidth(graph: StageGraph, containerWidth: number): number {
  const columns = Math.max(1, ...[...graph.placement.values()].map((place) => place.col))
  return Math.min(COLUMN_MAX, Math.max(COLUMN_MIN, (containerWidth - PAD_X * 2) / columns))
}

export function mapGeometry(graph: StageGraph, column: number): MapGeometry {
  const places = [...graph.placement.values()]
  const hasTop = places.some((place) => place.row === -1)
  const hasBottom = places.some((place) => place.row === 1)
  const mainY = TOP_SPACE + (hasTop ? ROW_GAP - 24 : 0)
  const rowY = { [-1]: mainY - ROW_GAP + 24, 0: mainY, 1: mainY + ROW_GAP } as Record<-1 | 0 | 1, number>

  const points = new Map<StageKey, StagePoint>()
  for (const [key, place] of graph.placement) {
    points.set(key, { x: PAD_X + place.col * column, y: rowY[place.row], row: place.row })
  }

  const r = STAGE_RADIUS
  const edges: EdgeLine[] = []
  const drawn = new Set<string>()
  for (const edge of graph.edges) {
    const a = points.get(edge.from)
    const b = points.get(edge.to)
    if (!a || !b || drawn.has(`${edge.from}>${edge.to}`)) continue
    const both = graph.edges.some((other) => other.from === edge.to && other.to === edge.from)
    // Пару «туда-обратно» рисуем одной линией от этапа основной линии
    if (both && a.row !== 0 && b.row === 0) continue
    drawn.add(`${edge.from}>${edge.to}`)
    drawn.add(`${edge.to}>${edge.from}`)

    const dir = Math.sign(b.x - a.x) || 1
    let line: Point[]
    if (a.row === b.row && a.row !== 1 && Math.abs(b.x - a.x) <= column * 1.01) {
      line = [
        [a.x + dir * r, a.y],
        [b.x - dir * r, b.y],
      ]
    } else if (a.row === b.row && a.row !== 1) {
      // Пропуск этапа или возврат назад по линии — дугой сверху, возврат выше
      const top = a.y - (dir > 0 ? SKIP_HEIGHT : SKIP_HEIGHT + 14)
      line = [
        [a.x, a.y - r],
        [a.x, top],
        [b.x, top],
        [b.x, b.y - r],
      ]
    } else if (a.row === 0 && b.row === -1) {
      line = [
        [a.x, a.y - r],
        [a.x, b.y],
        [b.x - dir * r, b.y],
      ]
    } else if (a.row === -1 && b.row === 0) {
      line = [
        [a.x + dir * r, a.y],
        [b.x, a.y],
        [b.x, b.y - r],
      ]
    } else if (a.row === 0 && b.row === 1) {
      // Вниз по просвету между колонками рядом с этапом, оттуда — к ответвлению
      const gap = a.x + (dir * column) / 2
      line =
        Math.abs(gap - b.x) < 1
          ? [
              [a.x + dir * r, a.y],
              [gap, a.y],
              [gap, b.y - r],
            ]
          : [
              [a.x + dir * r, a.y],
              [gap, a.y],
              [gap, b.y],
              [b.x - Math.sign(b.x - gap) * r, b.y],
            ]
    } else if (a.row === 1 && b.row === 0) {
      const gap = b.x - (dir * column) / 2
      line = [
        [a.x, a.y - r],
        [a.x, a.y - r - 8],
        [gap, a.y - r - 8],
        [gap, b.y],
        [b.x - dir * r, b.y],
      ]
    } else {
      const length = Math.hypot(b.x - a.x, b.y - a.y) || 1
      const ux = (b.x - a.x) / length
      const uy = (b.y - a.y) / length
      line = [
        [a.x + ux * r, a.y + uy * r],
        [b.x - ux * r, b.y - uy * r],
      ]
    }
    edges.push({ from: edge.from, to: edge.to, points: line, both })
  }

  const xs = [...points.values()].map((point) => point.x)
  return {
    width: Math.max(...xs) + PAD_X,
    height: rowY[hasBottom ? 1 : 0] + r + LABEL_SPACE,
    points,
    edges,
  }
}

/** SVG-путь по ломаной со скруглёнными углами */
export function roundedPath(points: readonly Point[], radius = 10): string {
  if (!points.length) return ''
  let path = `M ${points[0]![0]} ${points[0]![1]}`
  for (let index = 1; index < points.length - 1; index++) {
    const [px, py] = points[index - 1]!
    const [cx, cy] = points[index]!
    const [nx, ny] = points[index + 1]!
    const before = Math.hypot(cx - px, cy - py)
    const after = Math.hypot(nx - cx, ny - cy)
    const round = Math.min(radius, before / 2, after / 2)
    if (!round) continue
    const start = [cx - ((cx - px) / before) * round, cy - ((cy - py) / before) * round]
    const end = [cx + ((nx - cx) / after) * round, cy + ((ny - cy) / after) * round]
    path += ` L ${start[0]} ${start[1]} Q ${cx} ${cy} ${end[0]} ${end[1]}`
  }
  const last = points.at(-1)!
  return `${path} L ${last[0]} ${last[1]}`
}

export function lineLength(points: readonly Point[]): number {
  let total = 0
  for (let index = 1; index < points.length; index++) {
    total += Math.hypot(points[index]![0] - points[index - 1]![0], points[index]![1] - points[index - 1]![1])
  }
  return total
}

/** Точка на ломаной на расстоянии distance от начала — по ней едет красная точка */
export function pointAlong(points: readonly Point[], distance: number): Point {
  let left = Math.max(0, distance)
  for (let index = 1; index < points.length; index++) {
    const [ax, ay] = points[index - 1]!
    const [bx, by] = points[index]!
    const segment = Math.hypot(bx - ax, by - ay)
    if (left <= segment && segment > 0) return [ax + ((bx - ax) * left) / segment, ay + ((by - ay) * left) / segment]
    left -= segment
  }
  return points.at(-1) ?? [0, 0]
}

/** Путь красной точки между этапами: от центра к центру по линии перехода (или напрямую, если линии нет) */
export function hopLine(geometry: MapGeometry, from: StageKey, to: StageKey): Point[] {
  const a = geometry.points.get(from)
  const b = geometry.points.get(to)
  if (!a || !b) return []
  const direct = geometry.edges.find((edge) => edge.from === from && edge.to === to)
  const reverse = direct ? null : geometry.edges.find((edge) => edge.both && edge.from === to && edge.to === from)
  const middle = direct ? direct.points : reverse ? [...reverse.points].reverse() : []
  return [[a.x, a.y], ...middle, [b.x, b.y]]
}
