import { clamp } from '@/shared/lib'

/**
 * Знак «А» для анимации входа: контур в единицах 0–100 (по высоте) и его раскладка в окне.
 * Знак рисуется в окне по центру; масштабируется он вокруг перекладины, а не центра: так при
 * увеличении экран накрывает сплошная перекладина, а не треугольный просвет внутри буквы.
 */

/** Внешний контур и просвет буквы, x и y — 0…100 */
const OUTER: readonly (readonly [number, number])[] = [
  [0, 100],
  [36, 0],
  [64, 0],
  [100, 100],
  [73, 100],
  [66.34, 78],
  [33.66, 78],
  [27, 100],
]
const COUNTER: readonly (readonly [number, number])[] = [
  [39.7, 58],
  [50, 24],
  [60.3, 58],
]

/** Ширина буквы к высоте */
const ASPECT = 0.82
/** Центр перекладины по высоте: вокруг этой точки знак растёт */
const CROSSBAR = 68

/**
 * Точки на штрихах знака: сюда садятся буквы, прежде чем знак «впечатается».
 * Вершина, ноги, перекладина и стопы — внутри заливки, мимо просвета.
 */
const CONTOUR: readonly (readonly [number, number])[] = [
  [50, 10],
  [31, 40],
  [69, 40],
  [22, 64],
  [78, 64],
  [40, 68],
  [60, 68],
  [12, 90],
  [88, 90],
  [42, 22],
  [58, 22],
  [50, 68],
  [6, 97],
  [94, 97],
  [36, 52],
  [64, 52],
]

export interface Point {
  x: number
  y: number
}

export interface SignLayout {
  /** Видимый центр знака */
  center: Point
  /** Центр перекладины — точка, вокруг которой знак растёт */
  pivot: Point
  /** Высота знака, px */
  height: number
  /** Во сколько раз вырасти, чтобы перекладина накрыла всё окно */
  flood: number
  /** Радиус круга, который из центра открывает всё окно */
  reveal: number
}

/** Знак под размер окна: на телефоне меньше, на широком экране — не больше 240 px */
export function signLayout(width: number, height: number): SignLayout {
  const size = Math.round(clamp(Math.min(width * 0.36, height * 0.275), 120, 240))
  const unit = size / 100
  const center = { x: width / 2, y: height / 2 }
  const pivot = { x: center.x, y: center.y + (CROSSBAR - 50) * unit }
  // Перекладина — полоса ±10 единиц по высоте и не уже ±28 по ширине: она должна накрыть все края
  const flood = 1.2 * Math.max(Math.max(pivot.y, height - pivot.y) / (10 * unit), Math.max(center.x, width - center.x) / (28 * unit))
  const reveal = Math.hypot(Math.max(center.x, width - center.x), Math.max(center.y, height - center.y)) + 24
  return { center, pivot, height: size, flood, reveal }
}

function toWindow(layout: SignLayout, point: readonly [number, number], size = layout.height): Point {
  const unit = size / 100
  const pivotY = layout.center.y + (CROSSBAR - 50) * unit
  return { x: layout.center.x + (point[0] - 50) * ASPECT * unit, y: pivotY + (point[1] - CROSSBAR) * unit }
}

/** SVG-путь знака в координатах окна; `size` — высота, по умолчанию как у раскладки */
export function signPath(layout: SignLayout, size = layout.height): string {
  const line = (points: readonly (readonly [number, number])[]) =>
    points
      .map((point, index) => {
        const { x, y } = toWindow(layout, point, size)
        return `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(' ')
  return `${line(OUTER)} Z ${line(COUNTER)} Z`
}

/** Куда садится буква номер `index`: точки повторяются, если букв больше */
export function contourPoint(layout: SignLayout, index: number): Point {
  return toWindow(layout, CONTOUR[index % CONTOUR.length]!)
}
