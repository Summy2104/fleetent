import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { useIsMobile } from '@/hooks/use-mobile'

const originalWidth = window.innerWidth

function setViewportWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
}

afterEach(() => setViewportWidth(originalWidth))

describe('useIsMobile', () => {
  it('is false on a wide viewport', () => {
    setViewportWidth(1024)
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)
  })

  it('is true below the 768px breakpoint', () => {
    setViewportWidth(500)
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })
})
