import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { bootstrapFromArgs } from './settings/bootstrapFromArgs'

bootstrapFromArgs()

ReactDOM.createRoot(document.getElementById('root')).render(/* ... */)
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
