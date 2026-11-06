"""Deterministic, rule-based entity extraction for financial headlines.

Companies come from the curated symbol registry, organizations from a fixed list of
regulators, exchanges and institutions, and people from role patterns such as
"CEO Jensen Huang" or "Tim Cook, Apple's chief executive". No model is involved, so the
output is reproducible and explainable; it favours precision over recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from finsent.app.services.symbol_registry import SYMBOLS


_NAME_SUFFIXES = re.compile(
    r"\b(inc|corp|corporation|co|company|ltd|limited|plc|group|holdings|and co|& co)\.?$",
    re.IGNORECASE,
)
# First words too generic to identify a company on their own.
_GENERIC_FIRST_WORDS = {
    "american", "general", "united", "bank", "advanced", "applied", "texas", "southern", "public",
    "digital", "union", "state", "national", "first", "power", "oil", "indian", "tata", "bajaj",
    "hdfc", "icici", "adani", "sbi", "bharat", "hindustan", "jsw", "max", "colgate", "info",
    "intercontinental", "charles", "capital", "simon", "realty", "air", "eli", "johnson", "home",
    "walt", "electronic", "international", "kinder", "phillips", "lam", "kla", "dr", "marathon",
    "constellation", "estee", "mahindra", "one", "pb", "fsn", "life", "steel", "container", "page",
    "tech", "u.s.", "global", "data", "energy",
}
# Company names that are also everyday headline words need a stricter match.
_STRICT_ALIASES = {"target": re.compile(r"(?<![Pp]rice )\bTarget\b(?! [Pp]rice)")}

ORGANIZATIONS: tuple[str, ...] = (
    "SEC", "FTC", "DOJ", "Justice Department", "Federal Reserve", "Fed", "FDA", "Treasury",
    "European Commission", "EU", "ECB", "Bank of England", "Bank of Japan", "IMF", "World Bank",
    "OPEC", "WHO", "Pentagon", "Congress", "Senate", "White House", "Supreme Court", "CFTC", "FCC",
    "FAA", "NHTSA", "IRS", "RBI", "SEBI", "CCI", "NSE", "BSE", "Nasdaq", "NYSE", "S&P", "Moody's",
    "Fitch", "Commerce Department", "Labor Department",
)
_ORG_PATTERNS = [
    (org, re.compile(rf"(?<![A-Za-z]){re.escape(org)}(?![A-Za-z])")) for org in sorted(ORGANIZATIONS, key=len, reverse=True)
]

_ROLE = r"(?i:CEO|CFO|COO|CTO|chief executive(?: officer)?|chief financial officer|chairman|chairwoman|chair|founder|co-founder|president)"
# First and last name, optionally with a middle initial. Headlines are often Title Case,
# so a longer run of capitalised words cannot be told apart from the verb that follows.
_PERSON = r"([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z'\-]+)"
_PERSON_PATTERNS = (
    re.compile(rf"\b{_ROLE}\s+{_PERSON}\b"),
    re.compile(rf"{_PERSON},\s+(?:the\s+)?(?:[A-Z][\w'&.]*\s+)?{_ROLE}\b"),
    re.compile(rf"{_PERSON}\s+(?i:said|says|told|warned|warns|sees|expects|predicts|thinks|believes|takes|slams)\b"),
)
_NOT_PEOPLE = {"Wall Street", "The Company", "Federal Reserve", "White House", "Supreme Court", "Last Week"}
# Words that end a capitalised phrase which is a role or a thing, not a person's surname.
_NOT_SURNAMES = {"analyst", "analysts", "strategist", "economist", "shares", "stock", "stocks", "report", "market", "markets", "investors"}


@dataclass(frozen=True, slots=True)
class Entities:
    companies: tuple[str, ...]
    people: tuple[str, ...]
    organizations: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        return {"companies": list(self.companies), "people": list(self.people), "organizations": list(self.organizations)}


def _clean_company_name(name: str) -> str:
    cleaned = name.strip().rstrip(".")
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _NAME_SUFFIXES.sub("", cleaned).strip().rstrip(",").strip()
    return cleaned


@lru_cache(maxsize=1)
def _company_aliases() -> tuple[tuple[re.Pattern[str], str], ...]:
    aliases: dict[str, str] = {}
    for symbol in SYMBOLS:
        canonical = _clean_company_name(symbol.display_name)
        if not canonical:
            continue
        aliases.setdefault(canonical.lower(), canonical)
        first = canonical.split()[0]
        if len(first) >= 4 and first.lower() not in _GENERIC_FIRST_WORDS and len(canonical.split()) > 1:
            aliases.setdefault(first.lower(), canonical)
    ordered = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)
    return tuple(
        (_STRICT_ALIASES.get(alias) or re.compile(rf"(?<![A-Za-z]){re.escape(alias)}(?:'s)?(?![A-Za-z])", re.IGNORECASE), name)
        for alias, name in ordered
    )


def extract_entities(text: str | None) -> Entities:
    if not text:
        return Entities((), (), ())
    companies: list[str] = []
    for pattern, name in _company_aliases():
        if name not in companies and pattern.search(text):
            companies.append(name)

    organizations = [org for org, pattern in _ORG_PATTERNS if pattern.search(text)]
    # Drop shorter forms covered by a longer match ("Fed" inside "Federal Reserve").
    organizations = [org for org in organizations if not any(org != other and org in other for other in organizations)]

    people: list[str] = []
    company_words = {word.lower() for name in companies for word in name.split()}
    for pattern in _PERSON_PATTERNS:
        for match in pattern.finditer(text):
            candidate = re.sub(r"\s+", " ", match.group(1)).strip()
            words = candidate.split()
            if (
                candidate in _NOT_PEOPLE
                or candidate in people
                or words[-1].lower() in _NOT_SURNAMES
                or any(word.lower() in company_words for word in words)
            ):
                continue
            if all(word[0].isupper() for word in words):
                people.append(candidate)
    return Entities(tuple(companies[:4]), tuple(people[:3]), tuple(organizations[:4]))
