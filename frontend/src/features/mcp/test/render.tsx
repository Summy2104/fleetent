import type * as React from 'react'
import { type RenderResult, render } from '@testing-library/react'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { ThemeProvider } from '@/app/theme'
import { Toaster } from '@/components/ui/sonner'
import { I18nProvider } from '@/i18n'

export const API_BASE_URL = 'http://fleetent.test'

export function renderMcp(ui: React.ReactElement): RenderResult {
  return render(
    <I18nProvider>
      <ThemeProvider>
        <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
          <AppQueryProvider>
            {ui}
            <Toaster />
          </AppQueryProvider>
        </AuthProvider>
      </ThemeProvider>
    </I18nProvider>
  )
}
