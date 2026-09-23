import { StrictMode, useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { ClerkProvider } from '@clerk/clerk-react';
import App from './App.tsx';
import { getClerkPublishableKey } from './clerkConfig';
import './index.css';

function Root() {
  const [key, setKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getClerkPublishableKey()
      .then((k) => {
        if (!cancelled) setKey(k);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="max-w-md text-center">
          <h2 className="text-lg font-semibold text-red-700 mb-2">
            Failed to load authentication
          </h2>
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
            {error}
          </p>
        </div>
      </div>
    );
  }

  if (!key) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-sm text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <ClerkProvider publishableKey={key}>
      <App />
    </ClerkProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
