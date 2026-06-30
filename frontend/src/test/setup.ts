import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from '@/test/msw/server'

// Node 26 ships an experimental native `globalThis.localStorage` getter that
// returns `undefined` unless `--localstorage-file` is passed; in vitest's jsdom
// setup `window === globalThis`, so that getter shadows the Storage jsdom would
// otherwise provide and any `window.localStorage.*` call throws. Install a tiny
// in-memory Storage so persistence-backed code (theme, i18n) and the tests that
// assert on it behave like a real browser.
class MemoryStorage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: new MemoryStorage(),
  configurable: true,
  writable: true,
})

// Base UI defers unmounting a popup (Dialog/Select/Menu/AlertDialog) until its
// close animation finishes, probing `element.getAnimations()`. jsdom never runs
// CSS animations nor fires `animationend`, so an exiting popup would linger in
// the DOM — stacking duplicate dialogs and leaving the background `aria-hidden`
// (inert), which breaks role queries on the next interaction. This is Base UI's
// official test escape hatch: skip animation waiting → synchronous mount/unmount.
;(globalThis as typeof globalThis & { BASE_UI_ANIMATIONS_DISABLED?: boolean }).BASE_UI_ANIMATIONS_DISABLED = true

// jsdom lacks the pointer-capture / scrollIntoView APIs that Base UI primitives
// (Select, DropdownMenu) call during pointer interactions. Stub them so component
// tests can drive those widgets without crashing.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

// Base UI primitives position their popups (Menu, Select, Dialog, …) with
// Floating UI, whose autoUpdate loop needs ResizeObserver; they also probe
// matchMedia for viewport/RTL. jsdom ships neither — stub them so those
// popups mount and open during component tests.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver
}
if (!globalThis.matchMedia) {
  globalThis.matchMedia = ((query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false
    },
  })) as unknown as typeof matchMedia
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
