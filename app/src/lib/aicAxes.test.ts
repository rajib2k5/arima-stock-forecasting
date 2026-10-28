import { describe, expect, it } from 'vitest'
import {
  AIC_AXIS_HEIGHT,
  buildAxes,
  defaultView,
  describeAxes,
  FIELD_OF_VIEW,
  floorLines,
  LABEL_OFFSET,
  motionSettings,
  ORDER_MAX,
  orderTicks,
  sceneKeyPoints,
  TITLE_OFFSET,
  type Vec3,
} from './aicAxes'

// Hand-worked oracles. Orders run 0..5, so there are 6 ticks per order axis (not 5, not 7):
// p = 0,1,2,3,4,5 along +x; q = 0,1,2,3,4,5 along +z; AIC runs up +y. One order step = 1 unit.
// Labels sit LABEL_OFFSET = 0.45 outside the floor edge; the p and q titles sit TITLE_OFFSET = 1.2 out.

describe('orderTicks', () => {
  it('lists every integer order from 0 to the max, inclusive', () => {
    expect(orderTicks(5)).toEqual([0, 1, 2, 3, 4, 5])
    expect(orderTicks(2)).toEqual([0, 1, 2])
    expect(orderTicks(0)).toEqual([0])
  })
  it('defaults to the 0..5 range the app shows', () => {
    expect(ORDER_MAX).toBe(5)
    expect(orderTicks()).toEqual([0, 1, 2, 3, 4, 5])
    expect(orderTicks()).toHaveLength(6)
  })
  it.each([-1, 2.5, NaN, Infinity])('refuses an invalid max %s', (bad) => {
    expect(() => orderTicks(bad)).toThrow(RangeError)
  })
})

describe('buildAxes (defaults: orders 0..5, AIC height 5)', () => {
  const axes = buildAxes()
  const byId = (id: string) => axes.find((a) => a.id === id)!

  it('has exactly the p, q and AIC axes, titled p, q and AIC', () => {
    expect(axes.map((a) => [a.id, a.title])).toEqual([
      ['p', 'p'],
      ['q', 'q'],
      ['aic', 'AIC'],
    ])
  })
  it('runs p along +x and q along +z from the origin, one unit per order', () => {
    expect(byId('p').start).toEqual([0, 0, 0])
    expect(byId('p').end).toEqual([5, 0, 0])
    expect(byId('q').start).toEqual([0, 0, 0])
    expect(byId('q').end).toEqual([0, 0, 5])
  })
  it('runs AIC up +y for the axis height and draws no ticks (there is no scale yet)', () => {
    expect(AIC_AXIS_HEIGHT).toBe(5)
    expect(byId('aic').end).toEqual([0, 5, 0])
    expect(byId('aic').ticks).toEqual([])
  })
  it('puts six ticks on p and on q, labelled 0..5, each exactly on its axis', () => {
    expect(byId('p').ticks).toHaveLength(6)
    expect(byId('q').ticks).toHaveLength(6)
    expect(byId('p').ticks.map((t) => t.label)).toEqual(['0', '1', '2', '3', '4', '5'])
    expect(byId('q').ticks.map((t) => t.value)).toEqual([0, 1, 2, 3, 4, 5])
    // p tick 3 is at x = 3 on the x axis; q tick 4 is at z = 4 on the z axis
    expect(byId('p').ticks[3].at).toEqual([3, 0, 0])
    expect(byId('q').ticks[4].at).toEqual([0, 0, 4])
    // first and last ticks coincide with the axis ends
    expect(byId('p').ticks[0].at).toEqual(byId('p').start)
    expect(byId('p').ticks[5].at).toEqual(byId('p').end)
    expect(byId('q').ticks[5].at).toEqual(byId('q').end)
  })
  it('pushes tick labels 0.45 outside the floor: p labels behind (-z), q labels to the left (-x)', () => {
    expect(LABEL_OFFSET).toBe(0.45)
    expect(byId('p').ticks[3].labelAt).toEqual([3, 0, -0.45])
    expect(byId('q').ticks[4].labelAt).toEqual([-0.45, 0, 4])
  })
  it('centres the p and q titles on their axes, 1.2 outside the floor, and the AIC title just above its tip', () => {
    expect(TITLE_OFFSET).toBe(1.2)
    // p title: middle of 0..5 is 2.5; 1.2 behind the floor edge, clear of the labels at 0.45
    expect(byId('p').titlePosition).toEqual([2.5, 0, -1.2])
    expect(byId('q').titlePosition).toEqual([-1.2, 0, 2.5])
    // AIC title: axis tip at y = 5, plus 0.45
    expect(byId('aic').titlePosition).toEqual([0, 5.45, 0])
  })
})

describe('buildAxes with custom sizes', () => {
  it('scales with the order max and the AIC height', () => {
    const axes = buildAxes(3, 2)
    expect(axes[0].end).toEqual([3, 0, 0])
    expect(axes[0].ticks).toHaveLength(4) // 0,1,2,3
    expect(axes[0].titlePosition).toEqual([1.5, 0, -1.2])
    expect(axes[1].end).toEqual([0, 0, 3])
    expect(axes[2].end).toEqual([0, 2, 0])
    expect(axes[2].titlePosition).toEqual([0, 2.45, 0])
  })
  it.each([0, -1, NaN, Infinity])('refuses an AIC height of %s', (h) => {
    expect(() => buildAxes(5, h)).toThrow(RangeError)
  })
  it('refuses an invalid order max', () => {
    expect(() => buildAxes(-2)).toThrow(RangeError)
  })
})

describe('floorLines', () => {
  const lines = floorLines()
  it('has one line per integer order in each direction: 2 * 6 = 12 for orders 0..5', () => {
    expect(lines).toHaveLength(12)
    expect(floorLines(2)).toHaveLength(6) // 3 + 3
    expect(floorLines(1)).toHaveLength(4)
  })
  it('runs the p = k lines along q first, then the q = k lines along p (hand-worked ends)', () => {
    expect(lines[0]).toEqual([[0, 0, 0], [0, 0, 5]]) // p = 0
    expect(lines[3]).toEqual([[3, 0, 0], [3, 0, 5]]) // p = 3
    expect(lines[5]).toEqual([[5, 0, 0], [5, 0, 5]]) // p = 5
    expect(lines[6]).toEqual([[0, 0, 0], [5, 0, 0]]) // q = 0
    expect(lines[8]).toEqual([[0, 0, 2], [5, 0, 2]]) // q = 2
    expect(lines[11]).toEqual([[0, 0, 5], [5, 0, 5]]) // q = 5
  })
  it('keeps every line on the floor, on integer coordinates, inside the 0..5 square', () => {
    for (const seg of lines) {
      for (const [x, y, z] of seg) {
        expect(y).toBe(0)
        for (const c of [x, z]) {
          expect(Number.isInteger(c)).toBe(true)
          expect(c).toBeGreaterThanOrEqual(0)
          expect(c).toBeLessThanOrEqual(5)
        }
      }
    }
  })
  it('runs every line through a p tick or a q tick, so grid and labels agree', () => {
    const p = buildAxes()[0].ticks.map((t) => t.at)
    const q = buildAxes()[1].ticks.map((t) => t.at)
    for (const [i, seg] of lines.entries()) {
      const startsOn = (ticks: Vec3[]) => ticks.some((t) => t[0] === seg[0][0] && t[1] === seg[0][1] && t[2] === seg[0][2])
      expect(startsOn(i < 6 ? p : q)).toBe(true)
    }
  })
  it('refuses an invalid max', () => {
    expect(() => floorLines(-1)).toThrow(RangeError)
  })
})

describe('sceneKeyPoints', () => {
  it('includes the far floor corner, every axis end and title, and every tick label', () => {
    const pts = sceneKeyPoints()
    const has = (v: Vec3) => pts.some((p) => p[0] === v[0] && p[1] === v[1] && p[2] === v[2])
    expect(has([5, 0, 5])).toBe(true)
    expect(has([5, 0, 0])).toBe(true)
    expect(has([0, 5, 0])).toBe(true)
    expect(has([0, 5.45, 0])).toBe(true) // AIC title
    expect(has([2.5, 0, -1.2])).toBe(true) // p title
    expect(has([3, 0, -0.45])).toBe(true) // p tick label 3
    expect(has([-0.45, 0, 5])).toBe(true) // q tick label 5
  })
})

describe('defaultView', () => {
  it('looks at the centre of the axes box (2.5, 2.5, 2.5) for the defaults', () => {
    expect(defaultView().target).toEqual([2.5, 2.5, 2.5])
    expect(defaultView(5, 3).target).toEqual([2.5, 1.5, 2.5])
    expect(defaultView().fov).toBe(FIELD_OF_VIEW)
  })
  it('sits outside the box in the +x/+y/+z octant', () => {
    const { position } = defaultView(5, 5)
    for (const c of position) expect(c).toBeGreaterThan(5)
  })
  it('keeps every key point inside the vertical field of view at every auto-rotate angle', () => {
    // Auto-rotate turns the camera about the vertical axis through the target. For each of 24
    // azimuths, the angle between the view direction and the direction to each key point must
    // stay within half the field of view.
    for (const [max, height] of [[5, 5], [3, 2], [8, 6]] as const) {
      const { position, target, fov } = defaultView(max, height)
      const dx = position[0] - target[0]
      const dz = position[2] - target[2]
      const r = Math.hypot(dx, dz)
      const base = Math.atan2(dz, dx)
      for (let k = 0; k < 24; k++) {
        const a = base + (k * 2 * Math.PI) / 24
        const cam: Vec3 = [target[0] + r * Math.cos(a), position[1], target[2] + r * Math.sin(a)]
        const look = [target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]]
        for (const p of sceneKeyPoints(max, height)) {
          const v = [p[0] - cam[0], p[1] - cam[1], p[2] - cam[2]]
          const cos = (v[0] * look[0] + v[1] * look[1] + v[2] * look[2]) / (Math.hypot(...v) * Math.hypot(...look))
          const deg = (Math.acos(cos) * 180) / Math.PI
          expect(deg).toBeLessThanOrEqual(fov / 2)
        }
      }
    }
  })
  it('reports the camera distance from the target', () => {
    const { position, target, distance } = defaultView()
    expect(Math.hypot(position[0] - target[0], position[1] - target[1], position[2] - target[2])).toBeCloseTo(distance, 9)
  })
  it('refuses invalid sizes', () => {
    expect(() => defaultView(-1, 5)).toThrow(RangeError)
    expect(() => defaultView(5, 0)).toThrow(RangeError)
  })
})

describe('describeAxes', () => {
  it('states the p and q ranges and which way AIC is read', () => {
    expect(describeAxes()).toEqual(['p: 0 to 5', 'q: 0 to 5', 'AIC: lower is better'])
    expect(describeAxes(3)).toEqual(['p: 0 to 3', 'q: 0 to 3', 'AIC: lower is better'])
  })
  it('refuses an invalid max', () => {
    expect(() => describeAxes(-1)).toThrow(RangeError)
  })
})

describe('motionSettings', () => {
  it('turns every kind of automatic motion off under reduced motion', () => {
    expect(motionSettings(true)).toEqual({ autoRotate: false, autoRotateSpeed: 0, enableDamping: false, frameloop: 'demand' })
  })
  it('auto-rotates gently, with a continuous render loop, otherwise', () => {
    const m = motionSettings(false)
    expect(m.autoRotate).toBe(true)
    expect(m.autoRotateSpeed).toBeGreaterThan(0)
    expect(m.autoRotateSpeed).toBeLessThanOrEqual(1)
    expect(m.enableDamping).toBe(true)
    expect(m.frameloop).toBe('always')
  })
})
