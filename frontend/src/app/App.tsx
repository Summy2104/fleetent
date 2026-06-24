import { BrowserRouter } from 'react-router-dom';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';
import { ThemeProvider } from '@/app/theme';
import { Toaster } from '@/components/ui/toaster';

export function App(): JSX.Element {
  return (
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
  );
}
