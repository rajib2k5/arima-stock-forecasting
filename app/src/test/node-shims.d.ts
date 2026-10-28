/**
 * Types for the few Node calls a test makes. The app is browser code, so its tsconfig loads no
 * Node typings; AicAxesScene.test.tsx reads the bundled font from disk to check which glyphs it
 * has, and needs exactly these three functions and `import.meta.dirname` (vitest provides all
 * four at run time). If `@types/node` is ever installed, delete this file.
 */
declare module 'node:fs' {
  export function readFileSync(path: string): Uint8Array
}
declare module 'node:path' {
  export function resolve(...segments: string[]): string
}
declare module 'node:zlib' {
  export function inflateSync(data: Uint8Array): Uint8Array
}
interface ImportMeta {
  readonly dirname: string
}
