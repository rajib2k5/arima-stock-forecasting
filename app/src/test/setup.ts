import '@testing-library/jest-dom/vitest'

// jsdom has no canvas: getContext is "not implemented" and logs an error on every call.
// Answer null, which is exactly what a browser without WebGL answers, so the 3D preview's
// fallback path is exercised quietly and deterministically.
HTMLCanvasElement.prototype.getContext = () => null
