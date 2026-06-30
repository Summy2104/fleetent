import { BrowserRouter } from 'react-router-dom'

import { AuthProvider } from '@/app/auth'
import { AppQueryProvider } from '@/app/query-client'
import { AdminRoutes } from '@/app/routes'
import { ThemeProvider } from '@/app/theme'
import { Toaster } from '@/components/ui/toaster'
import { I18nProvider } from '@/i18n'

export function App(): JSX.Element {
  return (
    <I18nProvider>
      <ThemeProvider>
        <AuthProvider baseUrl={window.location.origin}>
          <AppQueryProvider>
            <BrowserRouter basename="/admin/ui">
              <AdminRoutes />
            </BrowserRouter>
            <Toaster />
          </AppQueryProvider>
        </AuthProvider>
      </ThemeProvider>
    </I18nProvider>
  )
}
