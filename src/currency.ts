/**
 * Currency display helpers.
 *
 * The pipeline stores currency as an ISO 4217 code (ZAR, USD, EUR, ...).
 * This module maps codes to the symbol a human expects to see next to
 * a number, so the UI shows "R 300,767,092" instead of "$300,767,092"
 * for South African Rand documents.
 */

const CODE_TO_SYMBOL: Record<string, string> = {
  USD: "$",
  EUR: "\u20ac",
  GBP: "\u00a3",
  JPY: "\u00a5",
  CNY: "\u00a5",
  CHF: "CHF",
  CAD: "C$",
  AUD: "A$",
  NZD: "NZ$",
  HKD: "HK$",
  SGD: "S$",
  TWD: "NT$",
  ZAR: "R",
  INR: "\u20b9",
  BRL: "R$",
  MXN: "Mex$",
  ARS: "AR$",
  CLP: "CLP$",
  COP: "COL$",
  PEN: "S/",
  UYU: "$U",
  VEF: "Bs.",
  SEK: "kr",
  NOK: "kr",
  DKK: "kr",
  PLN: "z\u0142",
  CZK: "K\u010d",
  HUF: "Ft",
  RON: "lei",
  BGN: "\u043b\u0432",
  RUB: "\u20bd",
  TRY: "\u20ba",
  UAH: "\u20b4",
  ILS: "\u20aa",
  SAR: "\ufdfc",
  AED: "\u062f.\u0625",
  QAR: "\u0631.\u0642",
  KWD: "\u062f.\u0643",
  BHD: "\u062f.\u0628",
  OMR: "\u0631.\u0639.",
  JOD: "\u062f.\u0627",
  EGP: "E\u00a3",
  MAD: "\u062f.\u0645.",
  TND: "\u062f.\u062a",
  DZD: "\u062f.\u062c",
  NGN: "\u20a6",
  KES: "KSh",
  GHS: "\u20b5",
  KRW: "\u20a9",
  THB: "\u0e3f",
  VND: "\u20ab",
  PHP: "\u20b1",
  IDR: "Rp",
  MYR: "RM",
  PKR: "\u20a8",
  BDT: "\u09f3",
  LKR: "Rs",
  NPR: "\u20a8",
  KZT: "\u20b8",
  AZN: "\u20bc",
  GEL: "\u20be",
  AMD: "\u058f",
  MNT: "\u20ae",
  LAK: "\u20ad",
  CRC: "\u20a1",
  PYG: "\u20b2",
};

/** Return the display symbol for an ISO 4217 code (e.g. "ZAR" -> "R"). */
export function currencySymbol(code: string | null | undefined): string {
  if (!code) return "$";
  const upper = String(code).toUpperCase().trim();
  return CODE_TO_SYMBOL[upper] ?? upper;
}

/**
 * Format a numeric amount with the currency symbol for the given code.
 * Returns e.g. "R 300,767,092" or "$1,000,000".
 */
export function formatCurrency(
  amount: number | string | null | undefined,
  code: string | null | undefined,
): string {
  if (amount === null || amount === undefined || amount === "") return "\u2014";
  const n = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(n)) return String(amount);
  return `${currencySymbol(code)} ${n.toLocaleString("en-US")}`;
}
