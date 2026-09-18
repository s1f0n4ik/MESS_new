import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { bootstrapFromArgs } from './settings/bootstrapFromArgs'
import { SetupScreen } from './setup/SetupScreen'

// ?setup=1 — первый запуск: Rust не нашёл launch.json и просит выбрать роль.
const isSetup = new URLSearchParams(window.location.search).get('setup') === '1'

// Роль и адрес координатора приходят из аргументов запуска / launch.json
// через query главного окна и должны попасть в localSettings до первого рендера.
if (!isSetup) bootstrapFromArgs()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isSetup ? <SetupScreen /> : <App />}
  </React.StrictMode>
)