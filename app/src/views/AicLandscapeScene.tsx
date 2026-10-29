/**
 * The 3D AIC landscape of one d: a marker per (p, q) cell at the height of its AIC, a wireframe
 * joining neighbouring cells, and the M0 axes. Loaded lazily by AicLandscapeView, so three.js stays
 * out of the main bundle. Geometry comes from aicLandscape.ts and aicAxes.ts; this file only draws.
 *
 * Each status has its own marker, so a failure never looks like a fit: ok is a solid sphere, the
 * chosen model a larger sphere in the accent colour on a stem, not_converged a wireframe sphere,
 * near_unit_root an octahedron in the warning colour, and failed a cross below the floor (the floor is the lowest AIC).
 */
import { useMemo, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Billboard, Line, Octahedron, OrbitControls, Sphere, Text } from '@react-three/drei'
// Bundled, so labels never trigger troika's CDN fallback; AicLandscapeScene.test.tsx checks that
// every label stays within the font (Basic Latin only: AIC values use an ASCII minus).
import labelFont from '@fontsource/inter/files/inter-latin-400-normal.woff?url'
import { buildAxes, defaultView, floorLines, type MotionSettings, type Vec3 } from '../lib/aicAxes'
import { landscape, TREND_LABELS } from '../lib/aicLandscape'
import type { AicGrid, TrendCode } from '../lib/contract.order'
import { useThemeColors } from './hooks'

export interface LandscapeSceneProps {
  grid: AicGrid
  d: number
  trends: TrendCode[]
  motion: MotionSettings
}

const R = 0.11

function Label({ position, color, size, children }: { position: Vec3; color: string; size: number; children: ReactNode }) {
  return (
    <Billboard position={position}>
      <Text font={labelFont} fontSize={size} color={color} anchorX="center" anchorY="middle">
        {children}
      </Text>
    </Billboard>
  )
}

export default function AicLandscapeScene({ grid, d, trends, motion }: LandscapeSceneProps) {
  const colors = useThemeColors()
  const axes = useMemo(() => buildAxes(), [])
  const floor = useMemo(() => floorLines().flat(), [])
  const view = useMemo(() => defaultView(), [])
  const scape = useMemo(() => landscape(grid, d, trends), [grid, d, trends])
  const trendColor = (trend: TrendCode) => (trends.length > 1 && trend === 't' ? colors.accent : colors.muted)
  const label = `3D AIC landscape for d = ${d} (${trends.map((t) => TREND_LABELS[t]).join(' and ')}): p and q on the floor, AIC upward, so the lowest point is the best fit. Drag to rotate.`
  return (
    <div className="aic-canvas" role="img" aria-label={label}>
      <Canvas frameloop={motion.frameloop} camera={{ position: view.position, fov: view.fov }} dpr={[1, 2]}>
        <Line points={floor} segments color={colors.muted} lineWidth={1} transparent opacity={0.4} />
        {axes.map((axis) => (
          <group key={axis.id}>
            <Line points={[axis.start, axis.end]} color={colors.ink} lineWidth={1.5} />
            <Label position={axis.titlePosition} color={colors.ink} size={0.42}>
              {axis.title}
            </Label>
            {axis.ticks.map((t) => (
              <Label key={t.value} position={t.labelAt} color={colors.muted} size={0.3}>
                {t.label}
              </Label>
            ))}
          </group>
        ))}
        {scape.ticks.map((t) => (
          <Label key={t.value} position={t.labelAt} color={colors.muted} size={0.3}>
            {t.label}
          </Label>
        ))}
        {trends.map((trend) => {
          const points = scape.segments.filter((s) => s.trend === trend).flatMap((s) => [s.from, s.to])
          return points.length > 0 ? <Line key={trend} points={points} segments color={trendColor(trend)} lineWidth={1} transparent opacity={0.7} /> : null
        })}
        {scape.points.map(({ cell, position, selected }) => {
          const name = `cell d${cell.d} p${cell.p} q${cell.q} ${cell.trend} ${cell.status}${selected ? ' chosen' : ''}`
          const key = `${cell.trend}-${cell.p}-${cell.q}`
          if (cell.status === 'failed') {
            // Below the floor (FAILED_Y), where no AIC is: the floor itself is the lowest AIC.
            const [x, y, z] = position
            const s = 0.16
            return (
              <Line
                key={key}
                name={name}
                points={[
                  [x - s, y, z - s],
                  [x + s, y, z + s],
                  [x - s, y, z + s],
                  [x + s, y, z - s],
                ]}
                segments
                color={colors.down}
                lineWidth={2}
              />
            )
          }
          if (cell.status === 'near_unit_root') {
            return (
              <Octahedron key={key} name={name} args={[R * 1.3]} position={position}>
                <meshBasicMaterial color={colors.down} />
              </Octahedron>
            )
          }
          if (selected) {
            return (
              <group key={key}>
                <Line points={[[position[0], 0, position[2]], position]} color={colors.accent} lineWidth={1.5} />
                <Sphere name={name} args={[R * 1.8, 20, 14]} position={position}>
                  <meshBasicMaterial color={colors.accent} />
                </Sphere>
              </group>
            )
          }
          return (
            <Sphere key={key} name={name} args={[R, 16, 12]} position={position}>
              <meshBasicMaterial color={cell.status === 'ok' ? colors.teal : colors.muted} wireframe={cell.status === 'not_converged'} />
            </Sphere>
          )
        })}
        <OrbitControls
          makeDefault
          target={view.target}
          enablePan={false}
          // No zoom: the wheel and a two-finger swipe must scroll the page, not trap the reader in the canvas.
          enableZoom={false}
          minDistance={view.distance * 0.6}
          maxDistance={view.distance * 1.5}
          autoRotate={motion.autoRotate}
          autoRotateSpeed={motion.autoRotateSpeed}
          enableDamping={motion.enableDamping}
        />
      </Canvas>
    </div>
  )
}
