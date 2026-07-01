if (import.meta.env.DEV) {
  void import('react-grab')
}

import React from 'react'
import ReactDOM from 'react-dom/client'

import { App } from '@/app/App'
import '@/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
