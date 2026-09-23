import React, { useEffect, useState, useMemo } from 'react';
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
  TrendingUp,
  BarChart3,
  PieChart as PieIcon,
  ScatterChart as ScatterIcon,
} from 'lucide-react';
import {
  PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line,
  ScatterChart, Scatter,
  ResponsiveContainer,
} from 'recharts';

const TRACK_COLORS: Record<string, string> = {
  traditional: '#6B7280',
  islamic: '#10B981',
};

const TRACK_LABELS: Record<string, string> = {
  traditional: 'Traditional',
  islamic: 'Islamic',
};

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
    return () => {
      cancelled = true;
    };
  }, [selectedInvestorId]);

  const selectedInvestor = investors.find((i) => i.id === selectedInvestorId);

  // ---- Chart data derivation ------------------------------------------

  // 1. Fund count by track (pie)
  const trackSplit = useMemo(() => {
    if (!portfolio) return [];
    const counts: Record<string, number> = {};
    for (const row of portfolio.holdings) {
      const t = row.instrument.compliance_mode;
      counts[t] = (counts[t] || 0) + 1;
    }
    return Object.entries(counts).map(([name, value]) => ({
      name: TRACK_LABELS[name] || name,
      track: name,
      value,
    }));
  }, [portfolio]);

  // 2. Exposure per fund (bar)
  const byFundData = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.holdings.map((row) => ({
      name:
        row.instrument.issuer_name.length > 20
          ? row.instrument.issuer_name.slice(0, 18) + '...'
          : row.instrument.issuer_name,
      fullName: row.instrument.issuer_name,
      stake: row.holding.stake_amount,
      currency: row.instrument.currency,
      track: row.instrument.compliance_mode,
    }));
  }, [portfolio]);

  // 3. Cumulative exposure over time (line)
  const overTimeData = useMemo(() => {
    if (!portfolio || portfolio.holdings.length === 0) return [];
    const sorted = [...portfolio.holdings].sort((a, b) =>
      a.holding.acquired_at.localeCompare(b.holding.acquired_at),
    );
    let running = 0;
    return sorted.map((row, i) => {
      running += row.holding.stake_amount;
      return {
        index: i + 1,
        date: row.holding.acquired_at.slice(0, 10),
        cumulative: running,
        stake: row.holding.stake_amount,
        fund: row.instrument.issuer_name,
      };
    });
  }, [portfolio]);

  // 4. Ownership vs stake (scatter)
  const scatterData = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.holdings.map((row) => ({
      stake: row.holding.stake_amount,
      ownership: row.holding.ownership_percentage ?? 0,
      track: row.instrument.compliance_mode,
      fund: row.instrument.issuer_name,
      currency: row.instrument.currency,
    }));
  }, [portfolio]);

  // ---- Table grouping -------------------------------------------------
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
      {/* Header */}
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

      {/* Investor selector */}
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
          <Loader2 className="w-4 h-4 animate-spin" /> Loading portfolio...
        </div>
      )}

      {!loading && portfolio && (
        <>
          {/* Summary cards */}
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

          {/* Charts grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 1. Pie — Fund allocation by track */}
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-3">
                <PieIcon className="w-3.5 h-3.5 text-gray-400" />
                <h4 className="text-xs font-bold text-gray-900">
                  Allocation by Track
                </h4>
              </div>
              <div className="h-64">
                {trackSplit.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-xs text-gray-400">
                    No positions
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={trackSplit}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={((entry: any) => entry.name) as any}
                        labelLine={false}
                      >
                        {trackSplit.map((entry) => (
                          <Cell
                            key={entry.track}
                            fill={TRACK_COLORS[entry.track] || '#9CA3AF'}
                          />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
              <p className="text-[10px] text-gray-400 mt-2">
                Count of funds held, by compliance track
              </p>
            </div>

            {/* 2. Bar — Exposure per fund */}
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 className="w-3.5 h-3.5 text-gray-400" />
                <h4 className="text-xs font-bold text-gray-900">
                  Exposure per Fund
                </h4>
              </div>
              <div className="h-64">
                {byFundData.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-xs text-gray-400">
                    No positions
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={byFundData}
                      margin={{ top: 8, right: 8, left: 8, bottom: 40 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                      <XAxis
                        dataKey="name"
                        angle={-30}
                        textAnchor="end"
                        tick={{ fontSize: 10 }}
                        interval={0}
                        height={60}
                      />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip
                        formatter={((value: number, _n: string, item: any) =>
                          formatCurrency(value, item?.payload?.currency || 'USD')) as any}
                      />
                      <Bar dataKey="stake" radius={[4, 4, 0, 0]}>
                        {byFundData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={TRACK_COLORS[entry.track] || '#9CA3AF'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <p className="text-[10px] text-gray-400 mt-2">
                Each bar shows that fund's stake, in the fund's native currency
              </p>
            </div>

            {/* 3. Line — Cumulative exposure over time */}
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-3.5 h-3.5 text-gray-400" />
                <h4 className="text-xs font-bold text-gray-900">
                  Cumulative Exposure
                </h4>
              </div>
              <div className="h-64">
                {overTimeData.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-xs text-gray-400">
                    No positions
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={overTimeData}
                      margin={{ top: 8, right: 8, left: 8, bottom: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip
                        formatter={((value: number) =>
                          value.toLocaleString()) as any}
                        labelFormatter={((label: string, payload: any[]) =>
                          payload?.[0]?.payload?.fund
                            ? `${label} — ${payload[0].payload.fund}`
                            : label) as any}
                      />
                      <Line
                        type="monotone"
                        dataKey="cumulative"
                        stroke="#7048E8"
                        strokeWidth={2}
                        dot={{ r: 4, fill: '#7048E8' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
              <p className="text-[10px] text-gray-400 mt-2">
                Running total as positions were acquired (values mixed across currencies)
              </p>
            </div>

            {/* 4. Scatter — Ownership vs stake */}
            <div className="bg-white rounded-2xl p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-3">
                <ScatterIcon className="w-3.5 h-3.5 text-gray-400" />
                <h4 className="text-xs font-bold text-gray-900">
                  Ownership vs Stake
                </h4>
              </div>
              <div className="h-64">
                {scatterData.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-xs text-gray-400">
                    No positions
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                      <XAxis
                        type="number"
                        dataKey="stake"
                        name="Stake"
                        tick={{ fontSize: 10 }}
                      />
                      <YAxis
                        type="number"
                        dataKey="ownership"
                        name="Ownership"
                        unit="%"
                        tick={{ fontSize: 10 }}
                      />
                      <Tooltip
                        cursor={{ strokeDasharray: '3 3' }}
                        content={((props: any) => {
                          const p = props?.payload?.[0]?.payload;
                          if (!p) return null;
                          return (
                            <div className="bg-white border border-gray-200 rounded-lg p-2 text-[11px] shadow-sm">
                              <div className="font-bold text-gray-900 mb-1">
                                {p.fund}
                              </div>
                              <div className="text-gray-600">
                                Stake: {formatCurrency(p.stake, p.currency)}
                              </div>
                              <div className="text-gray-600">
                                Ownership: {p.ownership.toFixed(2)}%
                              </div>
                            </div>
                          );
                        }) as any}
                      />
                      <Scatter data={scatterData}>
                        {scatterData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={TRACK_COLORS[entry.track] || '#9CA3AF'}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                )}
              </div>
              <p className="text-[10px] text-gray-400 mt-2">
                Each point is one fund position — does a larger stake buy a larger share?
              </p>
            </div>
          </div>

          {/* Table */}
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
                          className={`border-t border-gray-100 ${
                            idx === 0 ? '' : 'bg-gray-50/40'
                          }`}
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
                            {formatCurrency(
                              row.holding.stake_amount,
                              row.instrument.currency,
                            )}
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
