// Types for checks.mjs, so the app's TypeScript tests can import it.
export declare const PREFIX: string
export declare const THEMES: readonly ('light' | 'dark')[]
export declare function fileName(section: string, theme: string, suffix?: string): string
export declare const BOUNDARY_TEXTS: readonly string[]
export declare const BLANK_SHARE: number
export declare function dominantShare(rgba: ArrayLike<number>): number
export declare function isBlank(rgba: ArrayLike<number>, share?: number): boolean
export declare const WALK_MIDDLE: readonly [number, number]
export declare function walkDay(status: string | null | undefined): { day: number; of: number } | null
export declare function labelPattern(label: string): RegExp

export interface PageFacts {
  theme?: string | null
  headings?: string[]
  alerts?: string[]
  statuses?: string[]
  text?: string
  pageErrors?: string[]
  canvas?: { width: number; height: number; rgba: ArrayLike<number> } | null
  walk?: { status: string | null; button: string | null } | null
  selected?: Record<string, string[]>
}
export interface ShotNeeds {
  theme: string
  heading: string
  canvas?: boolean
  walk?: boolean
  selected?: Record<string, string>
}
export declare function problems(page: PageFacts, expect: ShotNeeds): string[]
