import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig({
    base: '/admin/ui/',
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        host: '127.0.0.1',
        port: 4173,
        // Dev-only: forward admin API calls to the platform backend. The frontend
        // itself is served under /admin/ui, so bypass that prefix and proxy the rest.
        proxy: {
            '/admin': {
                target: 'http://127.0.0.1:8770',
                changeOrigin: true,
                bypass: function (req) {
                    var _a;
                    if ((_a = req.url) === null || _a === void 0 ? void 0 : _a.startsWith('/admin/ui')) {
                        return req.url;
                    }
                },
            },
        },
    },
    preview: {
        host: '127.0.0.1',
        port: 4173,
    },
});
