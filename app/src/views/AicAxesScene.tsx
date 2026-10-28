/**
 * The interactive 3D axes for the AIC landscape (milestone 2). Loaded lazily by
 * AicAxesPreview so three.js stays out of the main bundle. Draws geometry only: no data.
 */
import { useMemo, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Billboard, Line, OrbitControls, Text } from '@react-three/drei'
// Bundled with the app, so the labels load their font from our own files. troika-three-text fetches
// a fallback font from cdn.jsdelivr.net only for a character this font lacks, and no setting closes
// that path (`unicodeFontsURL` retries the CDN when its own URL fails). So labels stay within what
// the font covers, and AicAxesScene.test.tsx fails if one strays (a "φ" or "Δ", say).
import labelFont from '@fontsource/inter/files/inter-latin-400-normal.woff?url'
import { buildAxes, defaultView, floorLines, type MotionSettings, type Vec3 } from '../lib/aicAxes'
import { useThemeColors } from './hooks'

export interface SceneProps {
  motion: MotionSettings
}

function Label({ position, color, size, children }: { position: Vec3; color: string; size: number; children: ReactNode }) {
  return (
    <Billboard position={position}>
      <Text font={labelFont} fontSize={size} color={color} anchorX="center" anchorY="middle">
        {children}
      </Text>
    </Billboard>
  )
}

export default function AicAxesScene({ motion }: SceneProps) {
  const colors = useThemeColors()
  const axes = useMemo(() => buildAxes(), [])
  const floor = useMemo(() => floorLines().flat(), [])
  const view = useMemo(() => defaultView(), [])
  return (
    <div className="aic-canvas" role="img" aria-label="Empty 3D axes for the AIC landscape: p along one floor edge, q along the other, AIC upward. Drag to rotate.">
      <Canvas frameloop={motion.frameloop} camera={{ position: view.position, fov: view.fov }} dpr={[1, 2]}>
        <Line points={floor} segments color={colors.muted} lineWidth={1} transparent opacity={0.5} />
        {axes.map((axis) => (
          <group key={axis.id}>
            <Line points={[axis.start, axis.end]} color={colors.accent} lineWidth={2} />
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
        <OrbitControls
          makeDefault
          target={view.target}
          enablePan={false}
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
