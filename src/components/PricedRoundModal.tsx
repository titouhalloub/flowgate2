import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, TrendingUp } from 'lucide-react';
import {
  ApiRequestError,
  createPricedRound,
  previewPricedRound,
} from '../services/api';
import { PricedRound, PricedRoundPreview } from '../types';

// ---------------------------------------------------------------------------
// Phase 3.7 -- priced-round commit flow: terms -> preview -> result, one
// component.
//
// POST /priced-rounds/preview is a pure what-if (nothing persisted, no SAFE
// moves). Only "Commit round" writes, and the backend re-runs the same
// conversion math inside one transaction -- which is why the commit must be
// handed the identical pre_safe_shares / options_pool the preview was shown
// with, and why this modal owns those two values (never the preview response).
//
// A 4xx is a backend REFUSAL (bad terms, malformed date, ...): err.message goes
// to the parent's error box AND to the inline line here, and the modal stays on
// its step -- never silently swallowed. An outage gets a local retry line,
// because staying put with no message would look like the button did nothing.
// ---------------------------------------------------------------------------

type Step = 'terms' | 'preview' | 'result';

interface PricedRoundModalProps {
  isOpen: boolean;
  issuerName: string;
  /**
   * Pre-round assumptions. Left undefined by a parent that does not have them;
   * the modal then renders the two required inputs itself rather than guessing.
   */
  preSafeShares?: number;
  optionsPool?: number;
  onClose: () => void;
  onCommitted: (round: PricedRound) => void;
  onError: (message: string) => void;
}

function formatMoney(amount: number): string {
  return `$${amount.toLocaleString('en-US', { maximumFractionDigits: 4 })}`;
}

function formatShares(shares: number): string {
  return shares.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function isClientRejection(err: unknown): err is ApiRequestError {
  return err instanceof ApiRequestError && err.status >= 400 && err.status < 500;
}

export const PricedRoundModal: React.FC<PricedRoundModalProps> = ({
  isOpen,
  issuerName,
  preSafeShares,
  optionsPool,
  onClose,
  onCommitted,
  onError,
}) => {
  const [step, setStep] = useState<Step>('terms');
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  // Terms
  const [roundName, setRoundName] = useState('');
  const [pricePerShare, setPricePerShare] = useState(1.0);
  const [roundShares, setRoundShares] = useState(1000000);
  const [postMoneyShares, setPostMoneyShares] = useState(5000000);
  const [effectiveDate, setEffectiveDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [reviewer, setReviewer] = useState('');
  const [notes, setNotes] = useState('');
  // Rendered only when the parent did not supply the assumptions.
  const [preSafeSharesInput, setPreSafeSharesInput] = useState(0);
  const [optionsPoolInput, setOptionsPoolInput] = useState(0);

  const [preview, setPreview] = useState<PricedRoundPreview | null>(null);
  const [result, setResult] = useState<PricedRound | null>(null);

  const needsPreSafeShares = preSafeShares === undefined;
  const needsOptionsPool = optionsPool === undefined;
  const effectivePreSafeShares = preSafeShares ?? preSafeSharesInput;
  const effectiveOptionsPool = optionsPool ?? optionsPoolInput;

  // Latest callbacks behind refs: the 2s auto-close timer must not be reset (or
  // fire against a stale closure) just because the parent re-rendered and
  // handed us fresh function identities.
  const onCommittedRef = useRef(onCommitted);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCommittedRef.current = onCommitted;
    onCloseRef.current = onClose;
  }, [onCommitted, onClose]);

  // onCommitted fires at most once per committed round (the timer and the Close
  // button both route through it).
  const committedRoundIdRef = useRef<string | null>(null);
  const commitOnce = (round: PricedRound) => {
    if (committedRoundIdRef.current === round.id) return;
    committedRoundIdRef.current = round.id;
    onCommittedRef.current(round);
  };

  // Each open starts a fresh flow. The typed terms are deliberately kept so a
  // refused preview does not wipe the user's input.
  useEffect(() => {
    if (!isOpen) return;
    setStep('terms');
    setFormError('');
    setBusy(false);
    setPreview(null);
    setResult(null);
    committedRoundIdRef.current = null;
  }, [isOpen]);

  // Result step auto-commits after 2s if the user does not click Close.
  useEffect(() => {
    if (step !== 'result' || !result) return;
    const timer = window.setTimeout(() => {
      commitOnce(result);
      onCloseRef.current();
    }, 2000);
    return () => window.clearTimeout(timer);
    // commitOnce is stable for the lifetime of a given result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, result]);

  const handlePreview = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!roundName.trim()) {
      setFormError('Round name is required.');
      return;
    }
    if (!(pricePerShare > 0)) {
      setFormError('Price per share must be greater than zero.');
      return;
    }
    if (!Number.isInteger(roundShares) || roundShares <= 0) {
      setFormError('Round shares must be a whole number greater than zero.');
      return;
    }
    if (!Number.isInteger(postMoneyShares) || postMoneyShares <= 0) {
      setFormError('Post-money shares must be a whole number greater than zero.');
      return;
    }
    if (!effectiveDate) {
      setFormError('Effective date is required.');
      return;
    }
    if (!reviewer.trim()) {
      setFormError('A named reviewer signature is required.');
      return;
    }
    if (
      needsPreSafeShares &&
      (!Number.isInteger(preSafeSharesInput) || preSafeSharesInput < 0)
    ) {
      setFormError('Pre-SAFE shares are required (whole number, zero or more).');
      return;
    }
    if (
      needsOptionsPool &&
      (!Number.isInteger(optionsPoolInput) || optionsPoolInput < 0)
    ) {
      setFormError('Options pool is required (whole number, zero or more).');
      return;
    }
    // Declared post-money total must at least cover the shares it is made of.
    if (postMoneyShares < effectivePreSafeShares + effectiveOptionsPool + roundShares) {
      setFormError(
        'Post-money shares cannot be less than pre-SAFE shares + options pool + round shares.',
      );
      return;
    }

    setBusy(true);
    try {
      const whatIf = await previewPricedRound({
        issuer_name: issuerName,
        round_price: pricePerShare,
        pre_safe_shares: effectivePreSafeShares,
        options_pool: effectiveOptionsPool,
      });
      setPreview(whatIf);
      setStep('preview');
    } catch (err) {
      if (isClientRejection(err)) {
        setFormError(err.message);
        onError(err.message);
      } else {
        setFormError('Preview failed \u2014 the backend did not respond. Try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleCommit = async () => {
    setFormError('');
    setBusy(true);
    try {
      const round = await createPricedRound({
        issuer_name: issuerName,
        round_name: roundName.trim(),
        price_per_share: pricePerShare,
        round_shares: roundShares,
        // Identical assumptions the preview was shown with -- the backend
        // re-runs the conversion math in one transaction.
        pre_safe_shares: effectivePreSafeShares,
        options_pool: effectiveOptionsPool,
        effective_date: effectiveDate,
        reviewer: reviewer.trim(),
        notes: notes.trim() || undefined,
        client_request_id: crypto.randomUUID(),
      });
      setResult(round);
      setStep('result');
    } catch (err) {
      if (isClientRejection(err)) {
        setFormError(err.message);
        onError(err.message);
      } else {
        setFormError('Commit failed \u2014 the backend did not respond. Nothing was written.');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!isOpen) return null;

  const totalNewShares = preview?.total_new_shares ?? 0;
  const projectedFullyDiluted =
    effectivePreSafeShares + effectiveOptionsPool + totalNewShares;

  return (
    <div className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-gray-100 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-xs max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-gray-100 pb-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#EBE7FD] text-[#7048E8] flex items-center justify-center">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900">Record a Priced Round</h3>
              <p className="text-[11px] text-gray-500">
                {step === 'terms' && 'Step 1 of 3 — round terms'}
                {step === 'preview' && 'Step 2 of 3 — conversion preview (nothing written yet)'}
                {step === 'result' && 'Step 3 of 3 — round committed'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 cursor-pointer text-sm"
          >
            ✕
          </button>
        </div>

        {formError && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600" />
            <span>{formError}</span>
          </div>
        )}

        {/* ---------- Step 1: terms ---------- */}
        {step === 'terms' && (
          <form onSubmit={handlePreview} className="space-y-3">
            <div>
              <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                ROUND NAME (required)
              </label>
              <input
                type="text"
                value={roundName}
                onChange={(e) => setRoundName(e.target.value)}
                placeholder="Series A"
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  PRICE PER SHARE (required)
                </label>
                <input
                  type="number"
                  step={0.01}
                  min={0}
                  value={pricePerShare}
                  onChange={(e) => setPricePerShare(parseFloat(e.target.value) || 0)}
                  className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                />
              </div>
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  ROUND SHARES (required)
                </label>
                <input
                  type="number"
                  step={1}
                  min={1}
                  value={roundShares}
                  onChange={(e) => setRoundShares(parseInt(e.target.value, 10) || 0)}
                  className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                />
              </div>
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  POST-MONEY SHARES (required)
                </label>
                <input
                  type="number"
                  step={1}
                  min={1}
                  value={postMoneyShares}
                  onChange={(e) => setPostMoneyShares(parseInt(e.target.value, 10) || 0)}
                  className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                />
              </div>
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  EFFECTIVE DATE (required)
                </label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                />
              </div>
            </div>

            {/* Assumption inputs render only when the parent did not supply
                them -- the modal never guesses pre-SAFE shares or pool size. */}
            {(needsPreSafeShares || needsOptionsPool) && (
              <div className="grid grid-cols-2 gap-3 border border-gray-200 rounded-xl p-3 bg-gray-50/50">
                {needsPreSafeShares && (
                  <div>
                    <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                      PRE-SAFE SHARES (required)
                    </label>
                    <input
                      type="number"
                      step={1}
                      min={0}
                      value={preSafeSharesInput}
                      onChange={(e) => setPreSafeSharesInput(parseInt(e.target.value, 10) || 0)}
                      className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                    />
                  </div>
                )}
                {needsOptionsPool && (
                  <div>
                    <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                      OPTIONS POOL (required)
                    </label>
                    <input
                      type="number"
                      step={1}
                      min={0}
                      value={optionsPoolInput}
                      onChange={(e) => setOptionsPoolInput(parseInt(e.target.value, 10) || 0)}
                      className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                    />
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                REVIEWER SIGNATURE (required)
              </label>
              <input
                type="text"
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Sarah Jenkins"
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
              />
            </div>

            <div>
              <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                NOTES (optional)
              </label>
              <textarea
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-2 rounded-lg border border-gray-200 bg-white hover:bg-[#F4F6FC] text-gray-600 font-bold text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="px-4 py-2 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white font-bold text-xs shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {busy ? 'Previewing...' : 'Preview'}
              </button>
            </div>
          </form>
        )}
        {/* ---------- Step 2: preview (what-if, nothing written) ---------- */}
        {step === 'preview' && preview && (
          <div className="space-y-3">
            <div className="p-3 rounded-xl bg-[#F4F6FC] border border-gray-200 text-gray-700">
              <span className="font-bold text-gray-900">{preview.conversions.length}</span>
              {preview.conversions.length === 1 ? ' convertible will convert to ' : ' convertibles will convert to '}
              <span className="font-bold text-gray-900">{formatShares(preview.total_new_shares)}</span>
              {' shares.'}
            </div>

            <div className="overflow-x-auto border border-gray-100 rounded-xl">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-100 bg-[#FAFAFE]">
                    <th className="px-3 py-2.5">Holder</th>
                    <th className="px-3 py-2.5 text-right">Cap Price</th>
                    <th className="px-3 py-2.5 text-right">Discount Price</th>
                    <th className="px-3 py-2.5">Chosen Basis</th>
                    <th className="px-3 py-2.5 text-right">Shares Issued</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.conversions.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-gray-400">
                        No outstanding convertibles -- nothing to convert.
                      </td>
                    </tr>
                  )}
                  {preview.conversions.map((c) => (
                    <tr key={c.convertible_id} className="border-b border-gray-50 last:border-0">
                      <td className="px-3 py-2.5 font-semibold text-gray-900">
                        {c.investor_name}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                        {c.cap_price === null ? '\u2014' : formatMoney(c.cap_price)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-600">
                        {c.discount_price === null ? '\u2014' : formatMoney(c.discount_price)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                            c.pricing_basis === 'cap'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-[#EBE7FD] text-[#7048E8] border-purple-200/60'
                          }`}
                        >
                          {c.pricing_basis}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-900">
                        {formatShares(c.shares_issued)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="text-[11px] text-gray-500">
              Post-round fully-diluted shares:{' '}
              <span className="font-mono text-gray-700">
                {formatShares(projectedFullyDiluted)}
              </span>
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setStep('terms')}
                className="px-3 py-2 rounded-lg border border-gray-200 bg-white hover:bg-[#F4F6FC] text-gray-600 font-bold text-xs transition-colors cursor-pointer"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleCommit}
                disabled={busy}
                className="px-4 py-2 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white font-bold text-xs shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {busy ? 'Committing...' : 'Commit round'}
              </button>
            </div>
          </div>
        )}
        {/* ---------- Step 3: result ---------- */}
        {step === 'result' && result && (
          <div className="py-6 flex flex-col items-center text-center gap-3">
            <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <p className="text-sm font-bold text-gray-900">
              {`Round "${result.round_name}" committed.`}
            </p>
            <p className="text-xs text-gray-600 max-w-md">
              {`${result.conversions.length} convertibles converted to `}
              <span className="font-mono">{formatShares(result.total_conversion_shares)}</span>
              {' shares.'}
            </p>
            <button
              type="button"
              onClick={() => {
                commitOnce(result);
                onClose();
              }}
              className="mt-1 px-4 py-2 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white font-bold text-xs shadow-xs cursor-pointer"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
