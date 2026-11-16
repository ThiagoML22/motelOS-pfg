import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ToastProvider } from './components/ui/Toast'
import EntradaQR from './components/EntradaQR'
import VistaCliente from './components/VistaCliente'

// La página del cliente no pide sesión ni forma parte de la aplicación del personal. Se abre con el enlace del ticket
// (?cliente=), con el QR fijo de la habitación (?habitacion=) o con el QR para sumar otro celular (?sumar=).
const parametros = new URLSearchParams(window.location.search)
const tokenCliente = parametros.get('cliente')
const qrHabitacion = parametros.get('habitacion')
const invitacion = parametros.get('sumar')

const pagina = tokenCliente ? (
  <VistaCliente token={tokenCliente} />
) : qrHabitacion || invitacion ? (
  <EntradaQR qr={qrHabitacion ?? undefined} invitacion={invitacion ?? undefined} />
) : (
  <App />
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>{pagina}</ToastProvider>
  </React.StrictMode>,
)
