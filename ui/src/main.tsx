import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { KnowledgebaseApp } from './knowledgebase/KnowledgebaseApp.tsx'
import { loadUiSettings } from './utils/time'

const params = new URLSearchParams(window.location.search)

// Load UI timezone setting before rendering so the first paint uses correct
// formatting. Fire-and-forget: defaults apply until the fetch resolves, and a
// rerender happens automatically because React reads the live value via the
// formatter functions on each render.
void loadUiSettings()

createRoot(document.getElementById('root')!).render(
  params.get('knowledgebase') === '1'
    ? <KnowledgebaseApp />
    : <App />
)
