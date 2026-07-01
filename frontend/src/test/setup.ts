import { focusManager } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from '@/test/msw/server'

// React Query refetches all active queries when the window regains focus
// (`refetchOnWindowFocus` defaults to true). `userEvent` dispatches real focus
// events while driving dialogs/menus, so those background refetches fire at
// unpredictable moments; under CPU contention they can land outside a test's
// expected request window and trip MSW's `onUnhandledRequest: 'error'`. Replace
// the focus listener with a no-op so interactions never trigger stray refetches.
focusManager.setEventListener(() => () => {})

// vitest.config raises the whole-test timeout to 60s for the heavy Base UI
// dialog/menu flows, but Testing Library's findBy*/waitFor still default to
// 1000ms — far too tight when CI is CPU-starved and a menu/dialog needs >1s to
// mount (observed: a full run stretched to ~6x its usual wall-clock). Raise the
// async-util timeout so interaction polls tolerate slow hosts; the 60s test
// timeout still bounds a genuinely stuck test.
configure({ asyncUtilTimeout: 5000 })

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
