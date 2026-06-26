import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from '@/test/msw/server';

// Node 26 ships an experimental native `globalThis.localStorage` getter that
// returns `undefined` unless `--localstorage-file` is passed; in vitest's jsdom
// setup `window === globalThis`, so that getter shadows the Storage jsdom would
// otherwise provide and any `window.localStorage.*` call throws. Install a tiny
// in-memory Storage so persistence-backed code (theme, i18n) and the tests that
// assert on it behave like a real browser.
class MemoryStorage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: new MemoryStorage(),
  configurable: true,
  writable: true,
});

// jsdom lacks the pointer-capture / scrollIntoView APIs that Radix UI primitives
// (Select, DropdownMenu) call during pointer interactions. Stub them so component
// tests can drive those widgets without crashing.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
