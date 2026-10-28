/**
 * Geometry for the (p, q, AIC) axes of the milestone-2 AIC landscape: where the axis lines,
 * tick labels, floor grid and default camera sit. Pure numbers only; the react-three-fiber
 * scene (`src/views/AicAxesScene.tsx`) just draws what is computed here.
 *
 * Scene coordinates (three.js is Y-up): p runs along +x, q along +z, AIC along +y. One order
 * step is one scene unit, so the floor is a max-by-max grid whose lines fall on the integers.
 * The AIC axis carries no ticks: no data is drawn yet, so there is no scale to label.
 */

export type Vec3 = [number, number, number]

/** Highest ARIMA order shown on the p and q axes (orders 0..5). */
export const ORDER_MAX = 5
/** Height of the AIC axis in scene units. */
export const AIC_AXIS_HEIGHT = 5
/** How far tick labels sit outside the floor, in scene units. */
export const LABEL_OFFSET = 0.45
/** How far the p and q axis titles sit outside the floor: clear of the tick labels. */
export const TITLE_OFFSET = 1.2
/** Vertical field of view of the camera, in degrees. */
export const FIELD_OF_VIEW = 45

export interface AxisTick {
  value: number
  label: string
  /** Where the tick sits on the axis line. */
  at: Vec3
  /** Where its label is drawn, pushed outside the floor. */
  labelAt: Vec3
}

export interface AxisSpec {
  id: 'p' | 'q' | 'aic'
  title: string
  start: Vec3
  end: Vec3
  titlePosition: Vec3
  ticks: AxisTick[]
}

function assertOrderMax(max: number): void {
  if (!Number.isInteger(max) || max < 0) throw new RangeError(`order max must be a non-negative integer, got ${max}`)
}

function assertHeight(height: number): void {
  if (!Number.isFinite(height) || height <= 0) throw new RangeError(`AIC axis height must be positive, got ${height}`)
}

/** Integer tick values 0..max inclusive (max + 1 of them). */
export function orderTicks(max: number = ORDER_MAX): number[] {
  assertOrderMax(max)
  return Array.from({ length: max + 1 }, (_, i) => i)
}

export function buildAxes(max: number = ORDER_MAX, height: number = AIC_AXIS_HEIGHT): AxisSpec[] {
  assertHeight(height)
  const values = orderTicks(max)
  const mid = max / 2
  return [
    {
      id: 'p',
      title: 'p',
      start: [0, 0, 0],
      end: [max, 0, 0],
      titlePosition: [mid, 0, -TITLE_OFFSET],
      ticks: values.map((v) => ({ value: v, label: String(v), at: [v, 0, 0], labelAt: [v, 0, -LABEL_OFFSET] })),
    },
    {
      id: 'q',
      title: 'q',
      start: [0, 0, 0],
      end: [0, 0, max],
      titlePosition: [-TITLE_OFFSET, 0, mid],
      ticks: values.map((v) => ({ value: v, label: String(v), at: [0, 0, v], labelAt: [-LABEL_OFFSET, 0, v] })),
    },
    {
      id: 'aic',
      title: 'AIC',
      start: [0, 0, 0],
      end: [0, height, 0],
      titlePosition: [0, height + LABEL_OFFSET, 0],
      ticks: [],
    },
  ]
}

export type Segment = [Vec3, Vec3]

/**
 * Floor grid as line segments, one per integer order in each direction, so every line runs
 * through a tick: p = k lines run along q, q = k lines run along p. 2 * (max + 1) segments.
 */
export function floorLines(max: number = ORDER_MAX): Segment[] {
  const values = orderTicks(max)
  return [
    ...values.map((k): Segment => [[k, 0, 0], [k, 0, max]]),
    ...values.map((k): Segment => [[0, 0, k], [max, 0, k]]),
  ]
}

/** Every point the camera must keep in frame: axis ends, titles, tick labels, floor corners. */
export function sceneKeyPoints(max: number = ORDER_MAX, height: number = AIC_AXIS_HEIGHT): Vec3[] {
  const points: Vec3[] = [[max, 0, max]]
  for (const axis of buildAxes(max, height)) {
    points.push(axis.start, axis.end, axis.titlePosition, ...axis.ticks.map((t) => t.labelAt))
  }
  return points
}

const VIEW_ELEVATION = (25 * Math.PI) / 180
const VIEW_AZIMUTH = (45 * Math.PI) / 180
/** Extra room around the key points, for text height and perspective. */
const VIEW_MARGIN = 1.15

/**
 * Camera looks at the middle of the axes box from the +x/+y/+z side, far enough back that every
 * key point stays inside the field of view however far auto-rotate has turned the scene
 * (rotation is about the vertical axis through the target, which keeps the distance fixed).
 */
export function defaultView(max: number = ORDER_MAX, height: number = AIC_AXIS_HEIGHT): { position: Vec3; target: Vec3; fov: number; distance: number } {
  assertOrderMax(max)
  assertHeight(height)
  const target: Vec3 = [max / 2, height / 2, max / 2]
  const radius = Math.max(...sceneKeyPoints(max, height).map((p) => Math.hypot(p[0] - target[0], p[1] - target[1], p[2] - target[2])))
  const distance = (radius * VIEW_MARGIN) / Math.sin((FIELD_OF_VIEW / 2) * (Math.PI / 180))
  return {
    position: [
      target[0] + distance * Math.cos(VIEW_ELEVATION) * Math.cos(VIEW_AZIMUTH),
      target[1] + distance * Math.sin(VIEW_ELEVATION),
      target[2] + distance * Math.cos(VIEW_ELEVATION) * Math.sin(VIEW_AZIMUTH),
    ],
    target,
    fov: FIELD_OF_VIEW,
    distance,
  }
}

/** Plain-text description of the axes, used where WebGL is unavailable. */
export function describeAxes(max: number = ORDER_MAX): string[] {
  assertOrderMax(max)
  return [`p: 0 to ${max}`, `q: 0 to ${max}`, 'AIC: lower is better']
}

export interface MotionSettings {
  autoRotate: boolean
  autoRotateSpeed: number
  enableDamping: boolean
  /** 'demand' renders only when something changes, so a still scene costs no frames. */
  frameloop: 'always' | 'demand'
}

/** Reduced motion means no auto-rotate, no damping glide, and no continuous render loop. */
export function motionSettings(reducedMotion: boolean): MotionSettings {
  if (reducedMotion) return { autoRotate: false, autoRotateSpeed: 0, enableDamping: false, frameloop: 'demand' }
  return { autoRotate: true, autoRotateSpeed: 0.6, enableDamping: true, frameloop: 'always' }
}
