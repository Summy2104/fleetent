import { BrowserRouter } from 'react-router-dom';

import { AuthProvider } from '@/app/auth';
import { AppQueryProvider } from '@/app/query-client';
import { AdminRoutes } from '@/app/routes';

export function App(): JSX.Element {
  return (
    <AuthProvider baseUrl={window.location.origin}>
      <AppQueryProvider>
        <BrowserRouter basename="/admin/ui">
          <AdminRoutes />
        </BrowserRouter>
      </AppQueryProvider>
    </AuthProvider>
  );
}
