import React, { useEffect, useState } from 'react';
import { Investor } from '../types';
import { InvestorPortfolio } from '../types';
import { getInvestorPortfolio, ApiRequestError } from '../services/api';
import { formatCurrency } from '../currency';
import {
  Users,
  Globe,
  Building2,
  Briefcase,
  Loader2,
} from 'lucide-react';

interface InvestorPortfolioViewProps {
  investors: Investor[];
}

export const InvestorPortfolioView: React.FC<InvestorPortfolioViewProps> = ({
  investors,
}) => {
  const [selectedInvestorId, setSelectedInvestorId] = useState<string>(
    investors[0]?.id ?? '',
  );
  const [portfolio, setPortfolio] = useState<InvestorPortfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedInvestorId) {
      setPortfolio(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getInvestorPortfolio(selectedInvestorId)
      .then((data) => {
        if (!cancelled) setPortfolio(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiRequestError && err.status >= 400 && err.status < 500) {
          setError(err.message);
        } else {
          setError('The backend did not respond.');
        }
        setPortfolio(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedInvestorId]);

  const selectedInvestor = investors.find((i) => i.id === selectedInvestorId);

  // Group holdings by issuer for the cross-fund view
  const byIssuer = new Map<string, InvestorPortfolio['holdings']>();
  if (portfolio) {
    for (const row of portfolio.holdings) {
      const key = row.instrument.issuer_name;
      const arr = byIssuer.get(key) ?? [];
      arr.push(row);
      byIssuer.set(key, arr);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-[#EBE7FD] text-[#7048E8] flex items-center justify-center">
            <Users className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-gray-900">Cross-Fund Portfolio</h3>
            <p className="text-[11px] text-gray-500">
              One investor across every fund and both compliance tracks
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-semibold text-gray-600">Investor</label>
        <select
          value={selectedInvestorId}
          onChange={(e) => setSelectedInvestorId(e.target.value)}
          className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white min-w-[220px]"
        >
          {investors.length === 0 && <option value="">No investors yet</option>}
          {investors.map((inv) => (
            <option key={inv.id} value={inv.id}>
              {inv.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading portfolio…
        </div>
      )}

      {!loading && portfolio && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-1">
                <Building2 className="w-3.5 h-3.5" /> Funds
              </div>
              <div className="text-lg font-bold text-gray-900">
                {portfolio.fund_count}
              </div>
            </div>
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-1">
                <Briefcase className="w-3.5 h-3.5" /> Traditional exposure
              </div>
              <div className="text-lg font-bold text-gray-900">
                {formatCurrency(portfolio.total_traditional_exposure, 'USD')}
              </div>
            </div>
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-1">
                <Globe className="w-3.5 h-3.5" /> Islamic exposure
              </div>
              <div className="text-lg font-bold text-gray-900">
                {formatCurrency(portfolio.total_islamic_exposure, 'USD')}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            {portfolio.holdings.length === 0 ? (
              <div className="p-6 text-center text-xs text-gray-400">
                {selectedInvestor?.name ?? 'This investor'} holds no positions yet.
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-[#F4F6FC] text-gray-600">
                  <tr>
                    <th className="text-left px-3 py-2 font-bold">Fund</th>
                    <th className="text-left px-3 py-2 font-bold">Track</th>
                    <th className="text-left px-3 py-2 font-bold">Instrument</th>
                    <th className="text-right px-3 py-2 font-bold">Stake</th>
                    <th className="text-right px-3 py-2 font-bold">Ownership</th>
                    <th className="text-left px-3 py-2 font-bold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {[...byIssuer.entries()].map(([issuer, rows]) => (
                    <React.Fragment key={issuer}>
                      {rows.map((row, idx) => (
                        <tr
                          key={row.holding.id}
                          className={`border-t border-gray-100 ${idx === 0 ? '' : 'bg-gray-50/40'}`}
                        >
                          <td className="px-3 py-2 text-gray-800">
                            {idx === 0 ? issuer : ''}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                                row.instrument.compliance_mode === 'islamic'
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {row.instrument.compliance_mode}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-gray-600">
                            {row.instrument.transaction_type}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-800 font-mono">
                            {formatCurrency(row.holding.stake_amount, row.instrument.currency)}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-600">
                            {row.holding.ownership_percentage != null
                              ? `${row.holding.ownership_percentage.toFixed(2)}%`
                              : '\u2014'}
                          </td>
                          <td className="px-3 py-2 text-gray-600">
                            {row.holding.status}
                          </td>
                        </tr>
                      ))}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
};
