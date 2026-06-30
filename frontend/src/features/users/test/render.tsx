import type * as React from 'react'
import { type RenderResult, render, screen } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { I18nProvider } from '@/i18n'

export const API_BASE_URL = 'http://fleetent.test'

export function renderUsers(ui: React.ReactElement): RenderResult {
  return render(
    <I18nProvider>
      <AuthProvider baseUrl={API_BASE_URL} initialToken="session-token">
        <AppQueryProvider>{ui}</AppQueryProvider>
      </AuthProvider>
    </I18nProvider>
  )
}

/** 从 Radix Select trigger 选项。 */
export async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  trigger: HTMLElement,
  optionName: string
): Promise<void> {
  await user.click(trigger)
  await user.click(await screen.findByRole('option', { name: optionName }))
}
