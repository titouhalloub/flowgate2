import { getApiBase } from './services/api';

let cached: string | null = null;

export async function getClerkPublishableKey(): Promise<string> {
  if (cached) return cached;

  // Build-time env var (works in dev and if Render bakes it in).
  const fromEnv = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
  if (fromEnv && typeof fromEnv === 'string' && fromEnv.startsWith('pk_')) {
    cached = fromEnv;
    return cached;
  }

  // Runtime fetch from the backend /config endpoint.
  const base = getApiBase();
  const res = await fetch(`${base}/config`);
  if (!res.ok) {
    throw new Error(`Failed to load /config (status ${res.status})`);
  }
  const data = await res.json();
  if (!data.clerk_publishable_key) {
    throw new Error('Backend returned empty clerk_publishable_key');
  }
  cached = data.clerk_publishable_key;
  return cached;
}
