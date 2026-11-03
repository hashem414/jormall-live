from __future__ import annotations

import re
from typing import Iterable, List, Mapping, Tuple


DESCRIPTOR_PREFIX = re.compile(r"^(?:a\s+|an\s+)?(?:new\s+)?(?:online\s+)?(?:store|company|brand|business|shop)\s+", re.I)


def _clean_company(value: str) -> str:
    value = re.split(r"\b(?:wants?|is offering|are offering|would like|needs?|to promote|promote|promoting|selling|sells|campaign)\b", value, maxsplit=1, flags=re.I)[0]
    value = DESCRIPTOR_PREFIX.sub("", value)
    value = re.sub(r"^called\s+", "", value, flags=re.I)
    return " ".join(value.strip(" ,.-").split())


def extract_advertisers(prompt: str) -> List[str]:
    patterns = [
        r"\bon behalf of\s+([A-Z][A-Za-z0-9&.' ]{1,80})",
        r"^campaign for\s+([A-Z][A-Za-z0-9&.' ]{1,80})",
        r"\b(?:a\s+)?(?:company|store|brand|business|shop)\s+called\s+([A-Z][A-Za-z0-9&.' ]{1,80})",
        r"^([A-Z][A-Za-z0-9&.' ]{1,80})\s+(?:wants? to promote|is offering|are offering)\b",
        r"^([A-Z][A-Za-z0-9&.' ]{1,80})\s+(?:selling|sells|promotes|offers|needs)\b",
    ]
    found: List[str] = []
    for pattern_index, pattern in enumerate(patterns):
        match = re.search(pattern, prompt.strip(), flags=re.I)
        if not match:
            continue
        if not match.group(1).strip()[:1].isupper():
            continue
        captured = _clean_company(match.group(1))
        for company in re.split(r"\s+(?:and|&)\s+", captured):
            company = _clean_company(company)
            if company and company.lower() not in {"promote", "campaign", "new"} and company not in found:
                found.append(company)
        if pattern_index < 3 and found:
            break
    return found


def build_company_alias_index(catalogue_companies: Iterable[str]) -> Mapping[str, str]:
    return {" ".join(company.lower().split()): company for company in catalogue_companies if company}


def match_advertisers(advertisers: Iterable[str], catalogue_companies: Iterable[str] | Mapping[str, str]) -> Tuple[List[str], int]:
    normalized = catalogue_companies if isinstance(catalogue_companies, Mapping) else build_company_alias_index(catalogue_companies)
    matches: List[str] = []
    comparisons = 0
    for advertiser in advertisers:
        comparisons += 1
        exact = normalized.get(" ".join(advertiser.lower().split()))
        if exact:
            matches.append(exact)
    return matches, comparisons
