import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { bootstrapFromArgs } from './settings/bootstrapFromArgs'

// Роль и адрес координатора приходят из аргументов запуска (--role, --server)
// и должны попасть в localSettings до первого рендера.
bootstrapFromArgs()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)