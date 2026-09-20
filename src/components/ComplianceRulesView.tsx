import React, { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { ComplianceRule } from '../types';
import { listComplianceRules, ApiRequestError } from '../services/api';
import { ComplianceRuleModal } from './ComplianceRuleModal';

export const ComplianceRulesView: React.FC = () => {
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorBoxMsg, setErrorBoxMsg] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [packageFilter, setPackageFilter] = useState<string>('all');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listComplianceRules()
      .then((rows) => {
        if (!cancelled) setRules(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiRequestError && err.status >= 400 && err.status < 500) {
          setErrorBoxMsg(err.message);
        } else {
          setErrorBoxMsg('The backend did not respond.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const packages = Array.from(new Set(rules.map((r) => r.package_name))).sort();
  const visibleRules = packageFilter === 'all'
    ? rules
    : rules.filter((r) => r.package_name === packageFilter);

  const sortedRules = [...visibleRules].sort((a, b) => {
    if (a.package_name !== b.package_name) return a.package_name.localeCompare(b.package_name);
    if (a.rule_name !== b.rule_name) return a.rule_name.localeCompare(b.rule_name);
    return b.version - a.version;
  });

  const severityPill = (s: string) => {
    if (s === 'blocking') return 'bg-red-100 text-red-700';
    if (s === 'review') return 'bg-amber-100 text-amber-700';
    return 'bg-gray-100 text-gray-600';
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-[#EBE7FD] text-[#7048E8] flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-gray-900">Compliance Rules</h3>
            <p className="text-[11px] text-gray-500">Versioned rule packages</p>
          </div>
          <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-[#EBE7FD] text-[#7048E8]">
            {rules.length} Rules
          </span>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="text-xs font-bold px-3 py-1.5 rounded-lg bg-[#7048E8] text-white hover:bg-[#5c3bc4] transition-colors cursor-pointer"
        >
          New Version
        </button>
      </div>

      <div className="flex items-center rounded-lg border border-gray-200 overflow-hidden w-fit">
        <button
          onClick={() => setPackageFilter('all')}
          className={`px-3 py-1.5 text-xs font-bold transition-colors cursor-pointer ${
            packageFilter === 'all'
              ? 'bg-[#7048E8] text-white'
              : 'bg-white text-gray-600 hover:bg-[#F4F6FC]'
          }`}
        >
          All
        </button>
        {packages.map((pkg) => (
          <button
            key={pkg}
            onClick={() => setPackageFilter(pkg)}
            className={`px-3 py-1.5 text-xs font-bold border-l border-gray-200 transition-colors cursor-pointer ${
              packageFilter === pkg
                ? 'bg-[#7048E8] text-white'
                : 'bg-white text-gray-600 hover:bg-[#F4F6FC]'
            }`}
          >
            {pkg}
          </button>
        ))}
      </div>

      {errorBoxMsg && (
        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
          {errorBoxMsg}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="p-6 text-center text-xs text-gray-400">Loading…</div>
        ) : sortedRules.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-400">
            No rules loaded. Click New Version to create the first.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-[#F4F6FC] text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-bold">Package</th>
                <th className="text-left px-3 py-2 font-bold">Rule</th>
                <th className="text-right px-3 py-2 font-bold">Version</th>
                <th className="text-left px-3 py-2 font-bold">Effective From</th>
                <th className="text-left px-3 py-2 font-bold">Effective To</th>
                <th className="text-left px-3 py-2 font-bold">Severity</th>
                <th className="text-left px-3 py-2 font-bold">Label</th>
                <th className="text-left px-3 py-2 font-bold">Active</th>
              </tr>
            </thead>
            <tbody>
              {sortedRules.map((rule) => (
                <tr
                  key={rule.id}
                  className={`border-t border-gray-100 ${rule.active ? '' : 'opacity-60'}`}
                >
                  <td className="px-3 py-2 text-gray-800">{rule.package_name}</td>
                  <td className="px-3 py-2 text-gray-800">{rule.rule_name}</td>
                  <td className="px-3 py-2 text-right text-gray-800">{rule.version}</td>
                  <td className="px-3 py-2 text-gray-600">{rule.effective_from}</td>
                  <td className="px-3 py-2 text-gray-600">{rule.effective_to ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${severityPill(rule.severity)}`}>
                      {rule.severity}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-800">{rule.label}</td>
                  <td className="px-3 py-2">
                    {rule.active ? (
                      <span className="text-green-700 font-bold">Active</span>
                    ) : (
                      <span className="text-gray-400">Inactive</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ComplianceRuleModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onCreated={() => {
          setShowModal(false);
          setRefreshKey((k) => k + 1);
        }}
        onError={(m) => setErrorBoxMsg(m)}
      />
    </div>
  );
};