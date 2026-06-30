import type * as React from 'react'
import { type RenderResult, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { I18nProvider } from '@/i18n'

export const API_BASE_URL = 'http://fleetent.test'

export function renderSkills(ui: React.ReactElement): RenderResult {
  return render(
    <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
      <AppQueryProvider>
        <I18nProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </I18nProvider>
      </AppQueryProvider>
    </AuthProvider>
  )
}
