import React, { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { getApiBase, authHeaders } from '../services/api';

interface ExportButtonProps {
  /** Backend path, e.g. "/export/ledger.csv" */
  path: string;
  /** Button label, e.g. "Export CSV" */
  label: string;
  /** Downloaded filename, e.g. "flowgate-ledger.csv" */
  filename: string;
  className?: string;
}

export const ExportButton: React.FC<ExportButtonProps> = ({
  path,
  label,
  filename,
  className,
}) => {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    const base = getApiBase().replace(/\/$/, '');
    if (!base) {
      alert('Backend not configured.');
      return;
    }
    setLoading(true);
    try {
      const headers = await authHeaders(false);
      const res = await fetch(`${base}${path}`, { headers });
      if (!res.ok) {
        throw new Error(`Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
      alert('Export failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={
        className ||
        'text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer flex items-center gap-1.5 disabled:opacity-50'
      }
    >
      {loading ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <Download className="w-3.5 h-3.5" />
      )}
      {label}
    </button>
  );
};
