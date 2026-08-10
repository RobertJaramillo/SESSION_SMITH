import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

async function start() {
  // Keep mocks as the default for UI-only work. Set VITE_USE_MOCKS=false to
  // connect /v1 requests to the FastAPI server through Vite's proxy.
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== 'false') {
    const { worker } = await import('./mocks/browser');
    await worker.start({ onUnhandledRequest: 'bypass' });
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

start();
