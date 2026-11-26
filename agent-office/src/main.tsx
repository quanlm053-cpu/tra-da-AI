import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import TicketOffice from './TicketOffice'
import LendingOffice from './LendingOffice'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {window.location.pathname.startsWith('/lending') ? <LendingOffice /> : <TicketOffice />}
  </StrictMode>,
)
