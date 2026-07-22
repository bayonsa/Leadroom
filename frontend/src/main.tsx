import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/dm-sans/index.css'
import '@fontsource-variable/public-sans/index.css'
import '@fontsource-variable/source-code-pro/index.css'
import './index.css'
import App from './App.tsx'
import { initializeTheme } from './theme.ts'

initializeTheme()

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><App /></BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
