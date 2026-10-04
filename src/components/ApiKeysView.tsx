import React, { useCallback, useEffect, useState } from 'react';
import { KeyRound, Plus, Copy, Ban, AlertTriangle } from 'lucide-react';
import { ApiKey, ApiKeyRole } from '../types';
import { listApiKeys, createApiKey, revokeApiKey, ApiRequestError } from '../services/api';

const ROLES: ApiKeyRole[] = ['viewer', 'reviewer', 'compliance_officer', 'admin'];

const fmt = (iso: string | null): string => (iso ? iso.slice(0, 10) : '--');

export const ApiKeysView: React.FC = () => {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState<ApiKeyRole>('viewer');
  const [expires, setExpires] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    listApiKeys()
      .then(setKeys)
      .catch((err) => {
        if (err instanceof ApiRequestError && err.status >= 400 && err.status < 500) {
          setErrorMsg(err.message);
        } else {
          setErrorMsg('The backend did not respond.');
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (!name.trim()) return setFormError('Name is required.');
    setSaving(true);
    try {
      const created = await createApiKey({
        name: name.trim(),
        role,
        expires_at: expires ? new Date(`${expires}T00:00:00Z`).toISOString() : null,
      });
      setPlaintext(created.key);
      setShowForm(false);
      setName('');
      setExpires('');
      setRole('viewer');
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not create the key.');
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await revokeApiKey(id);
      load();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Could not revoke the key.');
    }
  };
return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound size={20} />
          <h2 className="text-lg font-semibold">API Keys</h2>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-3 py-2 text-sm text-white"
        >
          <Plus size={16} /> Generate New Key
        </button>
      </div>

      {errorMsg && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {plaintext && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-3 text-sm">
          <div className="mb-2 flex items-center gap-2 font-medium text-amber-800">
            <AlertTriangle size={16} /> Copy this key now -- it will not be shown again.
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded bg-white px-2 py-1 text-xs">
              {plaintext}
            </code>
            <button
              onClick={() => { navigator.clipboard?.writeText(plaintext); setCopied(true); }}
              className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs"
            >
              <Copy size={14} /> {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              onClick={() => { setPlaintext(null); setCopied(false); }}
              className="rounded border px-2 py-1 text-xs"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-500">Loading keys...</p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-gray-500">No API keys yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="border-b text-xs uppercase text-gray-500">
            <tr>
              <th className="py-2">Name</th>
              <th>Prefix</th>
              <th>Role</th>
              <th>Created</th>
              <th>Last used</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} className="border-b">
                <td className="py-2">{k.name}</td>
                <td><code className="text-xs">{k.prefix}</code></td>
                <td>{k.role}</td>
                <td>{fmt(k.created_at)}</td>
                <td>{fmt(k.last_used_at)}</td>
                <td>{k.revoked_at ? 'Revoked' : 'Active'}</td>
                <td className="text-right">
                  {!k.revoked_at && (
                    <button
                      onClick={() => handleRevoke(k.id)}
                      className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-red-600"
                    >
                      <Ban size={14} /> Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 p-4">
          <form
            onSubmit={handleCreate}
            className="w-full max-w-sm space-y-3 rounded-lg bg-white p-5 shadow-xl"
          >
            <h3 className="text-base font-semibold">Generate API Key</h3>
            {formError && (
              <div className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
                {formError}
              </div>
            )}
            <label className="block text-sm">
              <span className="mb-1 block">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border px-2 py-1 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block">Role</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as ApiKeyRole)}
                className="w-full rounded border px-2 py-1 text-sm"
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block">Expires (optional)</span>
              <input
                type="date"
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
                className="w-full rounded border px-2 py-1 text-sm"
              />
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded border px-3 py-1.5 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded bg-gray-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {saving ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};