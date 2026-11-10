import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ToastProvider } from './components/ui/Toast'
import VistaCliente from './components/VistaCliente'

// El enlace del ticket abre la página del cliente, que no pide sesión ni forma parte de la aplicación del personal.
const tokenCliente = new URLSearchParams(window.location.search).get('cliente')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      {tokenCliente ? <VistaCliente token={tokenCliente} /> : <App />}
    </ToastProvider>
  </React.StrictMode>,
)
