import React, { useState } from 'react';
import { ComplianceRule } from '../types';
import { createComplianceRule, ApiRequestError } from '../services/api';

interface ComplianceRuleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (rule: ComplianceRule) => void;
  onError: (message: string) => void;
}

export const ComplianceRuleModal: React.FC<ComplianceRuleModalProps> = ({
  isOpen,
  onClose,
  onCreated,
  onError,
}) => {
  const [formError, setFormError] = useState('');
  const [packageName, setPackageName] = useState('');
  const [ruleName, setRuleName] = useState('');
  const [label, setLabel] = useState('');
  const [description, setDescription] = useState('');
  const [appliesTo, setAppliesTo] = useState('');
  const [findingCode, setFindingCode] = useState('');
  const [severity, setSeverity] = useState<'blocking' | 'review' | 'info'>('review');
  const [message, setMessage] = useState('');
  const [conditionText, setConditionText] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [createdBy, setCreatedBy] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!packageName.trim()) return setFormError('Package name is required.');
    if (!ruleName.trim()) return setFormError('Rule name is required.');
    if (!label.trim()) return setFormError('Label is required.');
    if (!findingCode.trim()) return setFormError('Finding code is required.');
    if (!message.trim()) return setFormError('Message is required.');
    if (!createdBy.trim()) return setFormError('created_by is required.');
    if (!effectiveFrom) return setFormError('Effective date is required.');

    let condition: Record<string, unknown>;
    try {
      condition = conditionText.trim() ? JSON.parse(conditionText) : {};
    } catch {
      return setFormError('Condition must be valid JSON.');
    }

    try {
      const rule = await createComplianceRule({
        package_name: packageName.trim(),
        rule_name: ruleName.trim(),
        label: label.trim(),
        description: description.trim() || null,
        applies_to: appliesTo.split(',').map((s) => s.trim()).filter(Boolean),
        finding_code: findingCode.trim(),
        severity,
        message: message.trim(),
        condition,
        effective_from: effectiveFrom,
        created_by: createdBy.trim(),
      });
      onCreated(rule);
    } catch (err) {
      const msg =
        err instanceof ApiRequestError && err.status >= 400 && err.status < 500
          ? err.message
          : 'Save failed — the backend did not respond.';
      setFormError(msg);
      onError(msg);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-gray-100 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl text-xs max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-gray-100 pb-3">
          <h3 className="text-base font-bold text-gray-900">New Rule Version</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 cursor-pointer text-sm"
          >
            ✕
          </button>
        </div>

        {formError && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700">
            {formError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-gray-700 mb-1">Package name</label>
              <input
                type="text"
                value={packageName}
                onChange={(e) => setPackageName(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
            <div>
              <label className="block font-bold text-gray-700 mb-1">Rule name</label>
              <input
                type="text"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
          </div>

          <div>
            <label className="block font-bold text-gray-700 mb-1">Label</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
            />
          </div>

          <div>
            <label className="block font-bold text-gray-700 mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-gray-700 mb-1">Applies to (comma-separated)</label>
              <input
                type="text"
                value={appliesTo}
                onChange={(e) => setAppliesTo(e.target.value)}
                placeholder="loan, sukuk"
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
            <div>
              <label className="block font-bold text-gray-700 mb-1">Finding code</label>
              <input
                type="text"
                value={findingCode}
                onChange={(e) => setFindingCode(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
          </div>

          <div>
            <label className="block font-bold text-gray-700 mb-1">Severity</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as 'blocking' | 'review' | 'info')}
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
            >
              <option value="blocking">blocking</option>
              <option value="review">review</option>
              <option value="info">info</option>
            </select>
          </div>

          <div>
            <label className="block font-bold text-gray-700 mb-1">Message</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={2}
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
            />
          </div>

          <div>
            <label className="block font-bold text-gray-700 mb-1">Condition (JSON)</label>
            <textarea
              value={conditionText}
              onChange={(e) => setConditionText(e.target.value)}
              rows={3}
              placeholder='{"field": "kyc_status", "equals": "cleared"}'
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-gray-700 mb-1">Effective from</label>
              <input
                type="date"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
            <div>
              <label className="block font-bold text-gray-700 mb-1">Created by</label>
              <input
                type="text"
                value={createdBy}
                onChange={(e) => setCreatedBy(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-200 rounded-lg"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 border border-gray-200 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="text-xs font-bold px-3 py-1.5 rounded-lg bg-[#7048E8] text-white hover:bg-[#5c3bc4] cursor-pointer"
            >
              Save Version
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};