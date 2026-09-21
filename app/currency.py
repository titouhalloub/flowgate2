"""Currency detection and ISO 4217 normalization.

Used by the LLM extractor to override the currency field when the
document text carries a clear marker the model missed or misidentified
(e.g. "R 300,767,092" is South African Rand, not USD).
"""

from __future__ import annotations

import re


_ISO_CODES = [
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "NZD",
    "HKD", "SGD", "ZAR", "INR", "BRL", "MXN", "RUB", "KRW", "TRY",
    "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "ILS",
    "SAR", "AED", "QAR", "KWD", "BHD", "OMR", "JOD", "EGP", "MAD",
    "TND", "DZD", "NGN", "KES", "GHS", "PHP", "THB", "VND", "IDR",
    "MYR", "PKR", "BDT", "LKR", "NPR", "TWD", "ARS", "CLP", "COP",
    "PEN", "UYU", "VEF",
]


_SYMBOL_PATTERNS = [
    (r"US\$\s*\d", "USD"),
    (r"C\$\s*\d", "CAD"),
    (r"A\$\s*\d", "AUD"),
    (r"NZ\$\s*\d", "NZD"),
    (r"HK\$\s*\d", "HKD"),
    (r"S\$\s*\d", "SGD"),
    (r"R\$\s*\d", "BRL"),
    (r"CN\u00a5\s*\d", "CNY"),
    (r"\bRMB\b", "CNY"),
    (r"\bRM\s*\d", "MYR"),
    (r"\bRp\s*\d", "IDR"),
    (r"\bRs\.?\s*\d", "INR"),
    (r"\bCHF\b", "CHF"),
    (r"\$\s*\d", "USD"),
    (r"\u20ac\s*\d", "EUR"),
    (r"\u00a3\s*\d", "GBP"),
    (r"\u00a5\s*\d", "JPY"),
    (r"\u20b9\s*\d", "INR"),
    (r"\u20bd\s*\d", "RUB"),
    (r"\u20a9\s*\d", "KRW"),
    (r"\u20ba\s*\d", "TRY"),
    (r"\u20aa\s*\d", "ILS"),
    (r"\ufdfc\s*\d", "SAR"),
    (r"\u0e3f\s*\d", "THB"),
    (r"\u20ab\s*\d", "VND"),
    (r"\u20b1\s*\d", "PHP"),
    (r"\u20a6\s*\d", "NGN"),
    (r"\u20b4\s*\d", "UAH"),
    (r"\u20b8\s*\d", "KZT"),
    (r"\u20bc\s*\d", "AZN"),
    (r"\u20be\s*\d", "GEL"),
    (r"\u058f\s*\d", "AMD"),
    (r"\u20a1\s*\d", "CRC"),
    (r"\u20b2\s*\d", "PYG"),
    (r"\u20b5\s*\d", "GHS"),
    (r"\u20ad\s*\d", "LAK"),
    (r"\u20ae\s*\d", "MNT"),
    (r"z\u0142\s*\d", "PLN"),
    (r"K\u010d\s*\d", "CZK"),
    (r"\bFt\s*\d", "HUF"),
    (r"\blei\s*\d", "RON"),
    (r"\u043b\u0432\s*\d", "BGN"),
    (r"\bR\s*\d", "ZAR"),
]


_NAME_TO_CODE = [
    ("south african rand", "ZAR"),
    ("brazilian real", "BRL"),
    ("united states dollar", "USD"),
    ("us dollar", "USD"),
    ("australian dollar", "AUD"),
    ("canadian dollar", "CAD"),
    ("new zealand dollar", "NZD"),
    ("hong kong dollar", "HKD"),
    ("singapore dollar", "SGD"),
    ("swiss franc", "CHF"),
    ("japanese yen", "JPY"),
    ("chinese yuan", "CNY"),
    ("renminbi", "CNY"),
    ("indian rupee", "INR"),
    ("pakistani rupee", "PKR"),
    ("sri lankan rupee", "LKR"),
    ("nepalese rupee", "NPR"),
    ("saudi riyal", "SAR"),
    ("emirati dirham", "AED"),
    ("uae dirham", "AED"),
    ("qatari riyal", "QAR"),
    ("kuwaiti dinar", "KWD"),
    ("bahraini dinar", "BHD"),
    ("omani rial", "OMR"),
    ("jordanian dinar", "JOD"),
    ("israeli shekel", "ILS"),
    ("turkish lira", "TRY"),
    ("russian ruble", "RUB"),
    ("russian rouble", "RUB"),
    ("south korean won", "KRW"),
    ("swedish krona", "SEK"),
    ("norwegian krone", "NOK"),
    ("danish krone", "DKK"),
    ("polish zloty", "PLN"),
    ("czech koruna", "CZK"),
    ("hungarian forint", "HUF"),
    ("romanian leu", "RON"),
    ("bulgarian lev", "BGN"),
    ("mexican peso", "MXN"),
    ("argentine peso", "ARS"),
    ("chilean peso", "CLP"),
    ("colombian peso", "COP"),
    ("peruvian sol", "PEN"),
    ("nigerian naira", "NGN"),
    ("kenyan shilling", "KES"),
    ("ghanaian cedi", "GHS"),
    ("egyptian pound", "EGP"),
    ("moroccan dirham", "MAD"),
    ("tunisian dinar", "TND"),
    ("algerian dinar", "DZD"),
    ("philippine peso", "PHP"),
    ("thai baht", "THB"),
    ("vietnamese dong", "VND"),
    ("indonesian rupiah", "IDR"),
    ("malaysian ringgit", "MYR"),
    ("taiwan dollar", "TWD"),
    ("euro", "EUR"),
    ("pound sterling", "GBP"),
    ("british pound", "GBP"),
    ("rand", "ZAR"),
    ("yen", "JPY"),
    ("yuan", "CNY"),
    ("rupees", "INR"),
    ("rupee", "INR"),
    ("shekel", "ILS"),
    ("real", "BRL"),
    ("peso", "MXN"),
    ("dollars", "USD"),
    ("dollar", "USD"),
    ("euros", "EUR"),
    ("pounds", "GBP"),
]


def detect_currency(text):
    """Return the ISO 4217 code detected in the text, or None."""
    if not text:
        return None
    for code in _ISO_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    for pattern, code in _SYMBOL_PATTERNS:
        if re.search(pattern, text):
            return code
    lower = text.lower()
    for name, code in _NAME_TO_CODE:
        if name in lower:
            return code
    return None


def normalize_currency(value, text=None):
    """Normalize an extracted currency value to an ISO code."""
    if value is not None:
        s = str(value).strip()
        if s:
            upper = s.upper()
            if upper in _ISO_CODES:
                return upper
            lower = s.lower()
            for name, code in _NAME_TO_CODE:
                if name == lower or name in lower:
                    return code
    if text:
        return detect_currency(text)
    return None
