"""
JorMall Order Processing Campaign List Recommendation Engine

This module converts segment-summary exports into a cleaned, deduplicated,
order-processing-friendly catalog, then recommends lists for a campaign.

Privacy note:
- The engine does not infer personal attributes from phone numbers.
- It only uses list/segment metadata already present in the export.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import os
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


MIN_KEEP_YEAR = 2020
DEFAULT_MAX_LISTS = 30
DEFAULT_MIN_QUANTITY = 0

COMPANY_ABOUT_CACHE_PATH = Path(__file__).resolve().parent / "data" / "company_about_cache.json"


def _cache_enabled() -> bool:
    return os.getenv("COMPANY_ABOUT_CACHE", "1").lower() not in ["0", "false", "no", "off"]


def _load_company_about_cache() -> Dict[str, Any]:
    if not _cache_enabled() or not COMPANY_ABOUT_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(COMPANY_ABOUT_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_company_about_cache(cache: Dict[str, Any]) -> None:
    if not _cache_enabled():
        return
    try:
        COMPANY_ABOUT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPANY_ABOUT_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Cache must never break recommendations.
        pass


def _company_about_cache_key(profile: Dict[str, Any], model: str) -> str:
    company = normalize_key(profile.get("company", ""))
    categories = normalize_key("|".join(profile.get("category_groups", [])[:5]))
    branches = normalize_key("|".join(profile.get("branches", [])[:10] + profile.get("cities", [])[:8] + profile.get("areas", [])[:8]))
    return hashlib.sha256(f"{model}|{company}|{categories}|{branches}".encode("utf-8")).hexdigest()[:24]

UNIQUE_LIST_KEYWORDS = [
    "armenian", "armenians", "أرمن", "ارمن",
    "school", "schools", "مدرسة", "مدارس",
    "university", "universities", "جامعة", "جامعات",
    "tawjihi", "توجيهي",
    "vip", "v.i.p", "premium list", "niche", "community", "club",
    "doctor", "doctors", "clinic", "hospital", "medical",
    "engineer", "engineers", "lawyer", "lawyers",
]



# Source-quality exclusion rules requested by Order Processing.
# These lists are not recommended because they are internal CRM/SMA/JorMall,
# manual/custom extracts that may duplicate official segments, reseller lists,
# or non-SMS/email-purpose lists.
DROP_SOURCE_PATTERNS = [
    ("SMA / CRM internal list", [r"\bsma\b", r"\bcrm\b", r"sales\s*management\s*application"]),
    ("JorMall internal list", [r"\bjormall\w*\b", r"\bjor\s*mall\w*\b", r"\bjormallnet\b", r"\bjormall\.net\b"]),
    ("Manual / customized list", [
        r"\bmanual\b", r"\bmanually\b", r"\bcustom\b", r"\bcustomized\b", r"\bcustomised\b",
        r"\bspecial\s*purpose\b", r"\bpurpose\s*list\b", r"\bclient\s*request\b", r"\bprivate\s*request\b",
        r"\btest\s+list\b", r"\btest\s+data\b", r"\bcustomer\s*data\s*base\b", r"\bcustomer\s*database\b",
        r"\bdata\s*base\b", r"\bdata\s*list\b", r"\bwhatsapp\s*customers\b", r"\bcash\s*customers\b",
    ]),
    ("Reseller list", [
        r"\breseller\b", r"\bresellers\b", r"\bmass\s*jo\b", r"\bmassjo\b",
        r"\boshak\s*qimam\b", r"\boshakqimam\b", r"\bqimam\b",
    ]),
    ("Email / non-SMS list", [r"\be[-\s]?mail\b", r"\bemail\b", r"\bmailing\s*list\b"]),
]


def source_exclusion_reason(*values: Any) -> str:
    """Return a human-readable drop reason for non-official/high-duplicate-risk sources.

    Matching is intentionally conservative and token/word-boundary based so a
    normal company name is not dropped because it merely contains similar letters.
    """
    text = normalize_key(" ".join(clean_text(v) for v in values if clean_text(v)))
    if not text:
        return "Keep - official/eligible source"
    for reason, patterns in DROP_SOURCE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.I):
                return f"Drop - {reason}"
    return "Keep - official/eligible source"

CATEGORY_KEYWORDS = {
    # These are the reduced, user-facing business category clusters used by
    # the dropdown, OpenAI prompt interpretation, and recommendation engine.
    "Restaurants & Cafes": ["restaurant", "restaurants", "cafe", "cafes", "coffee", "catering", "bakery", "bakeries", "food", "meal", "dining", "مطعم", "مطاعم", "كافيه", "قهوة"],
    "Fashion & Apparel": ["fashion", "men fashion", "women fashion", "clothes", "clothing", "apparel", "wear", "shoes", "bags", "boutique", "ملابس", "ازياء", "أزياء", "احذية", "رجالي", "نسائي"],
    "Beauty, Gifts & Jewelry": ["beauty", "cosmetic", "cosmetics", "salon", "saloons", "jewelry", "jewellery", "gift", "gifts", "flowers", "chocolate", "spa", "watches", "تجميل", "صالون", "مجوهرات", "هدايا"],
    "Automotive": ["car", "cars", "auto", "automotive", "vehicle", "garage", "tires", "motors", "سيارات", "سيارة", "كراج"],
    "Education & Students": ["school", "schools", "university", "universities", "college", "colleges", "academy", "education", "students", "student", "graduates", "tawjihi", "course", "training", "مدرسة", "مدارس", "جامعة", "تعليم", "تدريب", "توجيهي"],
    "Medical & Healthcare": ["medical", "clinic", "clinics", "doctor", "doctors", "hospital", "pharmacy", "pharmaceutical", "health", "labs", "optics", "عيادة", "طبيب", "مستشفى", "صيدلية"],
    "Finance & Insurance": ["bank", "banking", "finance", "financial", "loan", "credit", "insurance", "exchange", "بنك", "قرض", "تمويل", "تأمين"],
    "Retail, Malls & Shopping": ["mall", "malls", "shopping", "retail", "shop", "stores", "online shopping", "supermarket", "super market", "grocery", "مول", "مجمع", "سوبرماركت"],
    "Home, Furniture & Appliances": ["home accessories", "furniture", "appliances", "home electrics", "building materials", "kitchen", "decor", "household", "أثاث", "مفروشات"],
    "Electronics & Technology": ["electronics", "computer", "computers", "mobile", "tv", "software", "it", "networking", "database", "e-commerce", "e-business", "digital", "programmer", "technology"],
    "Travel, Hotels & Tourism": ["travel", "tourism", "hotel", "hotels", "flight", "trip", "reservation", "سفر", "سياحة", "فندق"],
    "Transport, Taxi & Delivery": ["taxi", "transport", "delivery", "courier", "cargo", "logistics", "تاكسي", "توصيل", "نقل"],
    "Sports & Fitness": ["gym", "fitness", "sports", "sport", "health club"],
    "Entertainment, Events & Leisure": ["entertainment", "event", "events", "cinema", "movie", "leisure", "games", "club", "clubs", "banqueting"],
    "Real Estate & Construction": ["real estate", "contractor", "contractors", "construction", "architecture", "architect", "engineering department", "building", "property", "leasing"],
    "Professional & Associations": ["engineer", "engineers", "lawyer", "lawyers", "association", "associations", "chamber", "agricultural", "chemical", "mechanical", "civil", "electrical", "telecommunications", "نقابة", "محامي", "مهندس"],
    "Government & Public Sector": ["government", "embassy", "embassies", "ministry", "ministries", "municipality", "public sector", "e-government"],
    "NGO, Charity & Community": ["ngo", "charity", "charities", "foundation", "foundations", "donors", "volunteer", "community", "armenian", "armenians", "أرمن", "ارمن"],
    "Parents & Family": ["parents", "family", "families", "kids", "children", "school students"],
    "Religious & Cultural": ["christian", "christians", "muslim", "muslims", "religious", "church", "mosque"],
    "Executives & Management": ["owner", "owners", "ceo", "gm", "general manager", "manager", "executive", "head", "leader", "director", "partner", "administration", "operation", "operations"],
    "Employees & Corporate": ["employee", "employees", "corporate", "company", "companies", "business", "account", "customer care", "customer service", "sales", "marketing", "finance department", "human resources", "recruitment"],
    "Agriculture & Industry": ["farmer", "farmers", "agriculture", "industry", "industrial", "mining", "geology", "manufacturing", "production", "export"],
    "General / Misc": ["general", "misc", "other", "na", "unknown"],
}

# Ordered rules: more specific clusters are checked before broad operational roles.
CATEGORY_CLUSTER_RULES = list(CATEGORY_KEYWORDS.items())


CLASS_DOWNGRADE_CHAIN = {
    "Upper": ["Economy Plus", "Economy", "Economy Minus", "Budget"],
    "Class A": ["Class B", "Class C"],
    "Economy Plus": ["Economy", "Economy Minus", "Budget"],
    "Middle": ["Economy", "Economy Minus", "Budget"],
    "Economy": ["Economy Minus", "Budget"],
    "Class B": ["Class C"],
    "Economy Minus": ["Budget"],
    "Budget": [],
    "AllClasses": [],
    "NA": [],
}

CLASS_TERMS = [
    "Economy Plus", "Economy Minus", "AllClasses", "All Classes", "Economy",
    "Upper", "Middle", "Budget", "Class A", "Class B", "Class C",
]

GENDER_TERMS = ["Mixed", "Male", "Female"]

CAMPAIGN_SCHEMA = {
    "name": "campaign_targeting_request",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "desired_company": {"type": "string"},
            "desired_companies": {"type": "array", "items": {"type": "string"}},
            "desired_category": {"type": "string"},
            "desired_gender": {"type": "string", "enum": ["Any", "Male", "Female", "Mixed", "NA"]},
            "desired_socioeconomic_class": {"type": "string"},
            "desired_age_range": {"type": "string"},
            "desired_city": {"type": "string"},
            "desired_area": {"type": "string"},
            "must_have_keywords": {"type": "array", "items": {"type": "string"}},
            "avoid_keywords": {"type": "array", "items": {"type": "string"}},
            "allow_class_downgrade": {"type": "boolean"},
            "allow_age_extension": {"type": "boolean"},
            "use_allclasses_only_as_backup": {"type": "boolean"},
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "desired_company", "desired_companies", "desired_category", "desired_gender", "desired_socioeconomic_class", "desired_age_range",
            "desired_city", "desired_area", "must_have_keywords", "avoid_keywords", "allow_class_downgrade",
            "allow_age_extension", "use_allclasses_only_as_backup", "reasoning_summary",
        ],
    },
    "strict": True,
}


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_key(value: Any) -> str:
    s = clean_text(value).lower()
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = s.replace("all classes", "allclasses")
    s = re.sub(r"[^0-9a-zA-Z\u0600-\u06FF/ -]+", "", s)
    return clean_text(s)



def strip_exclusive_prefix(value: Any) -> str:
    """Remove JorMall exclusive-list marker from display matching only."""
    return clean_text(value).lstrip("*").strip()


STOPWORDS = {
    "the", "and", "for", "to", "a", "an", "of", "in", "on", "with", "campaign", "send", "sms", "list", "lists",
    "want", "need", "needs", "required", "require", "target", "targeting", "audience", "all", "every", "please",
    "new", "release", "launch", "product", "promotion", "offer", "offers", "campaigns", "marketing",
    "company", "branch", "branches", "restaurant", "restaurants", "cafe", "cafes", "store", "stores", "mall", "city", "jordan", "amman",
    "fashion", "clothes", "clothing", "apparel", "group", "center", "centre", "shop", "shopping", "medical", "clinic", "school", "university",
    "automotive", "auto", "cars", "car", "upper", "middle", "economy", "plus", "minus", "budget", "allclasses", "class",
    "mixed", "male", "female", "west", "east", "north", "south", "all", "over", "coverage", "general", "misc",
}

# Words that describe an audience/intention, not a company owner. These are
# used to avoid treating generic requests such as "all university students"
# as if the user explicitly named a company.
AUDIENCE_ONLY_TERMS = {
    "student", "students", "university", "universities", "college", "colleges",
    "graduate", "graduates", "tawjihi", "school", "schools", "parents",
    "education", "educational", "academy", "academies", "pupils", "علمي", "ادبي",
}

EDUCATION_INTENT_TERMS = {
    "student", "students", "university", "universities", "college", "colleges",
    "graduate", "graduates", "tawjihi", "school", "schools", "education",
    "educational", "academy", "academies", "parents",
}

# Product/industry logic rules. These are deliberately keyword/evidence-based,
# not semantic/fuzzy. They map a campaign subject to the category groups and
# original-list keywords that must be present for a recommendation.
PRODUCT_INDUSTRY_INTENTS = [
    {
        "intent": "Mobile phones & consumer electronics",
        "triggers": [
            "iphone", "i phone", "apple phone", "smartphone", "smartphones", "mobile phone", "mobile phones",
            "mobile", "mobiles", "cell phone", "cell phones", "phone", "phones", "samsung", "huawei",
            "xiaomi", "oppo", "gadget", "gadgets", "electronics", "electronic", "tablet", "tablets",
        ],
        "categories": ["Electronics & Technology"],
        "must_have_keywords": [
            "iphone", "apple", "smartphone", "smartphones", "mobile", "mobiles", "phone", "phones",
            "electronics", "electronic", "gadget", "gadgets", "computer", "computers", "technology",
            "samsung", "huawei", "xiaomi", "oppo",
        ],
        "avoid_keywords": [
            "clinic", "restaurant", "cafe", "school", "university", "tawjihi", "fashion", "beauty",
            "supermarket", "super market", "grocery", "fuel", "gas station", "gas stations", "vehicle", "vehicles",
            "automotive", "parents", "children", "museum", "tablet data",
        ],
    },
    {
        "intent": "Cars & automotive",
        "triggers": ["car", "cars", "auto", "automotive", "vehicle", "vehicles", "tire", "tires", "garage", "motor"],
        "categories": ["Automotive"],
        "must_have_keywords": ["car", "cars", "auto", "automotive", "vehicle", "vehicles", "tires", "garage", "motors"],
        "avoid_keywords": ["restaurant", "cafe", "school", "university", "clinic"],
    },
]


def infer_product_industry_intent(prompt: Any) -> Dict[str, Any]:
    """Return a strict logical industry intent from explicit prompt keywords.

    This prevents the app from using semantic guesses. Example: "new iPhone
    release" must become mobile/electronics targeting, not a company match for
    rows that happen to contain the word "New".
    """
    text = normalize_key(prompt).lower()
    if not text:
        return {}
    for rule in PRODUCT_INDUSTRY_INTENTS:
        for trigger in rule["triggers"]:
            trig = normalize_key(trigger).lower()
            if not trig:
                continue
            # Phrase triggers match as substrings; single-token triggers must
            # appear as tokens so "phone" does not match unrelated fragments.
            if " " in trig:
                hit = trig in text
            else:
                hit = re.search(rf"(?<![0-9a-zA-Z]){re.escape(trig)}(?![0-9a-zA-Z])", text, flags=re.I) is not None
            if hit:
                return {
                    "logical_intent": rule["intent"],
                    "desired_category": list(rule["categories"]),
                    "must_have_keywords": list(rule["must_have_keywords"]),
                    "avoid_keywords": list(rule.get("avoid_keywords", [])),
                    "strict_category_match": True,
                    "strict_logical_match": True,
                    "reasoning_summary": f"Logical product/industry intent detected: {rule['intent']}.",
                }
    return {}


def lexical_tokens(value: Any) -> List[str]:
    text = normalize_key(strip_exclusive_prefix(value)).lower()
    tokens = re.findall(r"[0-9a-zA-Z\u0600-\u06FF]+", text)
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def is_audience_only_phrase(value: Any) -> bool:
    """True when a phrase is a generic target audience, not a company name.

    Example: "university students" should select Education & Students, but it
    should not trigger company-priority matching against a list named
    "***University students".
    """
    tokens = re.findall(r"[0-9a-zA-Z\u0600-\u06FF]+", normalize_key(strip_exclusive_prefix(value)).lower())
    useful = [t for t in tokens if len(t) >= 3]
    if not useful:
        return False
    audience_hits = sum(1 for t in useful if t in AUDIENCE_ONLY_TERMS)
    non_audience = [t for t in useful if t not in AUDIENCE_ONLY_TERMS and t not in STOPWORDS]
    return audience_hits >= 1 and len(non_audience) == 0


def has_strong_education_intent(value: Any) -> bool:
    text = normalize_key(value).lower()
    tokens = set(re.findall(r"[0-9a-zA-Z\u0600-\u06FF]+", text))
    return bool(tokens.intersection(EDUCATION_INTENT_TERMS))


def lexical_company_score(query: Any, company: Any, list_name: Any = "") -> int:
    """Score company/list-owner similarity using lexical overlap, not demographics.

    This lets the recommender prioritize a company mentioned in the request even
    when the manual demographic filters are incomplete or intentionally broad.
    """
    q = normalize_key(strip_exclusive_prefix(query)).lower()
    c = normalize_key(strip_exclusive_prefix(company)).lower()
    ln = normalize_key(strip_exclusive_prefix(list_name)).lower()
    if not q or not c:
        return 0

    # Exact/substring owner match is strongest.
    if c and c in q:
        return 100
    if ln and q in ln and len(q) >= 5:
        return 92
    if c and q in c and len(q) >= 5:
        return 88

    q_tokens = lexical_tokens(q)
    c_tokens = lexical_tokens(c)
    ln_tokens = lexical_tokens(ln)
    if not q_tokens or not c_tokens:
        return 0

    c_set = set(c_tokens)
    ln_set = set(ln_tokens)
    shared_company = c_set.intersection(q_tokens)
    shared_list = ln_set.intersection(q_tokens)
    coverage_company = len(shared_company) / max(1, len(c_set))
    coverage_query = len(shared_company) / max(1, len(set(q_tokens)))
    coverage_list = len(shared_list) / max(1, len(ln_set)) if ln_set else 0
    ratio_company = difflib.SequenceMatcher(None, q, c).ratio()
    ratio_list = difflib.SequenceMatcher(None, q, ln).ratio() if ln else 0

    score = max(
        int(coverage_company * 76 + coverage_query * 18),
        int(coverage_list * 68),
        int(max(ratio_company, ratio_list) * 82),
    )
    # A single distinctive token from the company name should still be visible.
    if shared_company and len(c_set) <= 2:
        score = max(score, 70)
    return min(score, 100)


def cluster_business_category(category: Any, company: Any = "", list_name: Any = "") -> str:
    """Map many raw category labels into a smaller operational cluster list.

    The raw category is still kept as `Original Category`; this function only
    creates a cleaner user-facing category for dropdowns and recommendations.
    """
    raw = clean_text(category)
    raw_lower = raw.lower()
    # Category clustering must be based mainly on the parsed business category,
    # not on company/location text. Otherwise words such as "University Street"
    # can wrongly convert a Shopping Online list into Education & Students.
    if not raw or raw_lower in ["na", "none", "unknown"]:
        return "General / Misc"

    raw_key = normalize_key(raw)
    for cluster_name, _keywords in CATEGORY_CLUSTER_RULES:
        if normalize_key(cluster_name) == raw_key:
            return cluster_name

    category_text = raw_lower
    # Mobile/electronics wording should not be swallowed by "home electrics"
    # under Home/Furniture. For campaigns like a new iPhone release, this must
    # remain an electronics/technology audience.
    if re.search(r"\b(electronics?|mobile|mobiles|phone|phones|smartphone|computer|computers|technology|software|it|gadget|gadgets)\b", category_text):
        return "Electronics & Technology"

    for cluster_name, keywords in CATEGORY_CLUSTER_RULES:
        for kw in keywords:
            kw_clean = clean_text(kw).lower()
            if kw_clean and kw_clean in category_text:
                return cluster_name

    # Only use company/list-name fallback when the raw category is truly vague.
    if raw_lower in ["misc", "general", "other"]:
        return "General / Misc"

    # Common role-heavy labels are operational B2B segments.
    if re.search(r"\b(manager|executive|head|leader|director|owner|ceo|gm|partner)\b", category_text):
        return "Executives & Management"
    if re.search(r"\b(employee|employees|corporate|company|companies|sales|marketing|finance|hr|human resources)\b", category_text):
        return "Employees & Corporate"

    return "General / Misc"

def split_dash_outside_parentheses(text: str) -> List[str]:
    """Split on ' - ' only when the separator is outside parentheses."""
    text = clean_text(text)
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and text[i:i+3] == " - ":
            part = clean_text("".join(buf))
            if part:
                parts.append(part)
            buf = []
            i += 3
            continue
        buf.append(ch)
        i += 1
    part = clean_text("".join(buf))
    if part:
        parts.append(part)
    return parts


def to_int_safe(value: Any) -> int:
    s = clean_text(value).replace(",", "")
    if not s:
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def stable_hash(text: str, length: int = 12) -> str:
    return hashlib.sha256(clean_text(text).encode("utf-8")).hexdigest()[:length]


def segment_id(segment: str) -> str:
    return "LST_" + stable_hash(segment, 12)


def parse_date(text: str) -> pd.Timestamp:
    m = re.search(r"\((\d{1,2}/\d{1,2}/\d{4})\)", clean_text(text))
    if not m:
        return pd.NaT
    return pd.to_datetime(m.group(1), dayfirst=True, errors="coerce")


def infer_city_and_area(location_hint: str) -> Tuple[str, str]:
    loc = clean_text(location_hint)
    low = loc.lower()
    if not loc or loc == "NA":
        return "NA", "NA"

    if "all over jordan" in low or "all jordan" in low:
        city = "All Jordan"
    elif "west/east" in low or "east/west" in low:
        city = "Amman - West/East"
    elif "west" in low:
        city = "Amman - West"
    elif "east" in low:
        city = "Amman - East"
    elif "irbid" in low:
        city = "Irbid"
    elif "zarqa" in low:
        city = "Zarqa"
    elif "aqaba" in low:
        city = "Aqaba"
    elif "madaba" in low:
        city = "Madaba"
    elif "salt" in low:
        city = "Salt"
    else:
        city = "NA"

    area = loc
    area = re.sub(r"\b(West/East|East/West|West|East|All Over Jordan|All Jordan)\b", "", area, flags=re.I)
    area = re.sub(r"\s*-\s*", " - ", area)
    area = clean_text(area.strip(" -/")) or "NA"
    return city, area


def is_unique_list(text: str) -> bool:
    low = clean_text(text).lower()
    return any(k.lower() in low for k in UNIQUE_LIST_KEYWORDS)


def is_exclusive_list(text: str) -> bool:
    """JorMall convention: list names prefixed with *** are exclusive lists."""
    return clean_text(text).startswith("***")


def normalize_class(value: str) -> str:
    v = clean_text(value)
    if v.lower() == "all classes":
        return "AllClasses"
    return v or "NA"


def normalize_age_range(value: str) -> str:
    m = re.search(r"(\d{1,3})\s*-\s*(\d{1,3})", clean_text(value))
    if not m:
        return "NA"
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi:
        lo, hi = hi, lo
    return f"{lo} - {hi}"


def parse_age_bounds(age_range: str) -> Tuple[Optional[int], Optional[int]]:
    m = re.search(r"(\d{1,3})\s*-\s*(\d{1,3})", clean_text(age_range))
    if not m:
        return None, None
    lo, hi = int(m.group(1)), int(m.group(2))
    return (min(lo, hi), max(lo, hi))


def range_contains(container_range: str, requested_range: str) -> bool:
    c1, c2 = parse_age_bounds(container_range)
    r1, r2 = parse_age_bounds(requested_range)
    if c1 is None or r1 is None:
        return False
    return c1 <= r1 and c2 >= r2


def ranges_overlap(a: str, b: str) -> bool:
    a1, a2 = parse_age_bounds(a)
    b1, b2 = parse_age_bounds(b)
    if a1 is None or b1 is None:
        return False
    return max(a1, b1) <= min(a2, b2)


def parse_segment_text(segment: str) -> Dict[str, Any]:
    """Parse the official segment naming convention robustly.

    Important: some company/list names contain bracketed ranges such as
    "Tamweelcom (7-30)" or "Tawjihi average (60-69)". Those are NOT the
    target audience age. The target audience details are parsed from the text
    after the official creation date, for example:
    Company - Location (17/07/2023) Mixed - Economy (25 - 65) - Financial Aid
    """
    s = clean_text(segment)

    date_matches = list(re.finditer(r"\((\d{1,2}/\d{1,2}/\d{4})\)", s))
    date_match = date_matches[-1] if date_matches else None
    dt = pd.NaT
    before_date = s
    after_date = ""
    if date_match:
        dt = pd.to_datetime(date_match.group(1), dayfirst=True, errors="coerce")
        before_date = clean_text(s[:date_match.start()].strip(" -"))
        after_date = clean_text(s[date_match.end():].strip(" -"))

    parts_before = split_dash_outside_parentheses(before_date)
    company = parts_before[0] if parts_before else (re.split(r"\s+\(", s)[0].strip() if s else "NA")
    location_hint = " - ".join(parts_before[1:]) if len(parts_before) > 1 else "NA"
    city, area = infer_city_and_area(location_hint)

    target_text = after_date or s

    gender = "NA"
    for g in GENDER_TERMS:
        if re.search(rf"\b{re.escape(g)}\b", target_text, flags=re.I):
            gender = g
            break

    socioeconomic = "NA"
    for c in sorted(CLASS_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", target_text, flags=re.I):
            socioeconomic = normalize_class(c)
            break

    age_range = "NA"
    # Audience age is taken from the metadata after the date, not from company names.
    m_age = re.search(r"\((\d{1,3}\s*-\s*\d{1,3})\)", target_text)
    if m_age:
        age_range = normalize_age_range(m_age.group(1))

    category = "NA"
    if m_age:
        category = clean_text(target_text[m_age.end():].lstrip(" -")) or "NA"
    else:
        target_parts = split_dash_outside_parentheses(target_text)
        # Remove known metadata tokens and keep the remaining right-most business category.
        cleaned_parts = []
        for part in target_parts:
            if part in GENDER_TERMS:
                continue
            if normalize_class(part) in CLASS_TERMS or part in CLASS_TERMS:
                continue
            cleaned_parts.append(part)
        if cleaned_parts:
            category = cleaned_parts[-1]

    if category.lower() in ["", "na", "none", "unknown"]:
        category = "Misc"

    original_category = category
    business_category_group = cluster_business_category(original_category, company=company, list_name=s)

    return {
        "List ID": segment_id(s),
        "List Name": s,
        "Company": company or "NA",
        "Location Hint": location_hint,
        "Created Date": dt.strftime("%Y-%m-%d") if not pd.isna(dt) else "NA",
        "Created Year": int(dt.year) if not pd.isna(dt) else np.nan,
        "Gender": gender,
        "Class": socioeconomic,
        "Age Range": age_range,
        # Category is now the reduced operational cluster used by the app.
        # The raw parsed category remains available for audit/export.
        "Category": business_category_group,
        "Business Category Group": business_category_group,
        "Original Category": original_category,
        "City / Coverage": city,
        "Area": area,
        "Unique / Special List": bool(is_unique_list(s)),
        "Exclusive Data": bool(is_exclusive_list(s)),
    }

def _top_values(series: pd.Series, limit: int = 8) -> List[str]:
    values = []
    for value in series.fillna("NA").astype(str):
        value = clean_text(value)
        if not value or value in ["NA", "nan"]:
            continue
        if value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def company_about_text(group: pd.DataFrame) -> str:
    """Create a local About summary per company from the available segment metadata."""
    if group is None or group.empty:
        return "No company profile available."
    company = clean_text(group["Company"].iloc[0]) if "Company" in group else "Company"
    qty = int(pd.to_numeric(group.get("Quantity", pd.Series(dtype=int)), errors="coerce").fillna(0).sum())
    list_count = int(len(group))
    locations = _top_values(group.get("Location Hint", pd.Series(dtype=str)), 10)
    cities = _top_values(group.get("City / Coverage", pd.Series(dtype=str)), 8)
    areas = _top_values(group.get("Area", pd.Series(dtype=str)), 10)
    cats = _top_values(group.get("Category", pd.Series(dtype=str)), 6)
    genders = _top_values(group.get("Gender", pd.Series(dtype=str)), 5)
    classes = _top_values(group.get("Class", pd.Series(dtype=str)), 6)
    ages = _top_values(group.get("Age Range", pd.Series(dtype=str)), 6)
    latest_date = clean_text(group.get("Created Date", pd.Series(dtype=str)).replace("NA", np.nan).dropna().max()) if "Created Date" in group else "NA"
    exclusive = int(group.get("Exclusive Data", pd.Series(dtype=bool)).astype(bool).sum()) if "Exclusive Data" in group else 0
    special = int(group.get("Unique / Special List", pd.Series(dtype=bool)).astype(bool).sum()) if "Unique / Special List" in group else 0

    parts = [f"{company}: {list_count:,} list(s), {qty:,} total records"]
    if latest_date and latest_date != "nan":
        parts.append(f"latest date {latest_date}")
    if locations:
        parts.append("branches/coverage: " + ", ".join(locations))
    elif cities or areas:
        parts.append("coverage: " + ", ".join(cities + areas))
    if cities:
        parts.append("cities: " + ", ".join(cities))
    if areas:
        parts.append("areas: " + ", ".join(areas))
    if cats:
        parts.append("business groups: " + ", ".join(cats))
    audience_bits = []
    if genders:
        audience_bits.append("gender " + "/".join(genders))
    if classes:
        audience_bits.append("class " + "/".join(classes))
    if ages:
        audience_bits.append("ages " + "/".join(ages))
    if audience_bits:
        parts.append("audience profile: " + "; ".join(audience_bits))
    if exclusive or special:
        parts.append(f"quality signals: {exclusive:,} exclusive and {special:,} special/unique list(s)")
    return ". ".join(parts) + "."


def add_company_about_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty or "Company" not in out:
        out["About"] = ""
        return out
    about_map: Dict[str, str] = {}
    for company, group in out.groupby("Company", dropna=False):
        about_map[company] = company_about_text(group)
    out["About"] = out["Company"].map(about_map).fillna("")
    return out


def company_profile_payload(df: pd.DataFrame, company: str, max_examples: int = 12) -> Dict[str, Any]:
    """Return structured company profile evidence for confirmation before list selection."""
    target = clean_text(company)
    if not target or target in ["Any", "NA"]:
        return {"available": False, "company": target or "Any", "about": "No company name was detected in the request."}

    ready = df[df.get("Ready for Recommendation", True)].copy() if "Ready for Recommendation" in df else df.copy()
    scored = ready.copy()
    scored["_company_score"] = scored.apply(lambda r: lexical_company_score(target, r.get("Company", ""), r.get("List Name", "")), axis=1)
    matches = scored[scored["_company_score"] >= 58].copy()
    profile_status = "Ready for recommendation"
    if matches.empty:
        # If the company exists only in stale/non-ready rows, still show the About card
        # for confirmation, but mark it clearly so Order Processing knows why the
        # final lists may fall back to broader category matches.
        all_scored = df.copy()
        all_scored["_company_score"] = all_scored.apply(lambda r: lexical_company_score(target, r.get("Company", ""), r.get("List Name", "")), axis=1)
        matches = all_scored[all_scored["_company_score"] >= 58].copy()
        profile_status = "Found in catalog but not ready under current cleaning/date rules"
    if matches.empty:
        return {
            "available": False,
            "company": target,
            "about": f"No clear company/list-owner match was found for '{target}' in the cleaned catalog.",
            "branches": [], "cities": [], "areas": [], "category_groups": [], "lists_found": 0, "total_quantity": 0,
        }
    matches = matches.sort_values(["_company_score", "Created Date", "Quantity"], ascending=[False, False, False])
    best_company = clean_text(matches.iloc[0].get("Company", target))
    best_group = matches[matches["Company"].map(lambda x: lexical_company_score(best_company, x) >= 70)].copy()
    if best_group.empty:
        best_group = matches
    total_qty = int(pd.to_numeric(best_group["Quantity"], errors="coerce").fillna(0).sum()) if "Quantity" in best_group else 0
    examples = best_group.head(max_examples)
    profile = {
        "available": True,
        "recommendation_status": profile_status,
        "company": best_company,
        "about": company_about_text(best_group),
        "branches": _top_values(best_group.get("Location Hint", pd.Series(dtype=str)), 12),
        "cities": _top_values(best_group.get("City / Coverage", pd.Series(dtype=str)), 10),
        "areas": _top_values(best_group.get("Area", pd.Series(dtype=str)), 12),
        "category_groups": _top_values(best_group.get("Category", pd.Series(dtype=str)), 8),
        "audience_genders": _top_values(best_group.get("Gender", pd.Series(dtype=str)), 6),
        "classes": _top_values(best_group.get("Class", pd.Series(dtype=str)), 8),
        "age_ranges": _top_values(best_group.get("Age Range", pd.Series(dtype=str)), 8),
        "lists_found": int(len(best_group)),
        "total_quantity": total_qty,
        "exclusive_lists": int(best_group.get("Exclusive Data", pd.Series(dtype=bool)).astype(bool).sum()) if "Exclusive Data" in best_group else 0,
        "special_lists": int(best_group.get("Unique / Special List", pd.Series(dtype=bool)).astype(bool).sum()) if "Unique / Special List" in best_group else 0,
        "latest_date": clean_text(best_group.get("Created Date", pd.Series(dtype=str)).replace("NA", np.nan).dropna().max()) if "Created Date" in best_group else "NA",
        "evidence_lists": [
            {
                "list_name": clean_text(row.get("List Name", "")),
                "quantity": int(row.get("Quantity", 0) or 0),
                "date": clean_text(row.get("Created Date", "")),
                "city": clean_text(row.get("City / Coverage", "")),
                "area": clean_text(row.get("Area", "")),
                "category": clean_text(row.get("Category", "")),
            }
            for _, row in examples.iterrows()
        ],
    }
    return profile


def _source_domain(url: Any) -> str:
    try:
        parsed = urlparse(clean_text(url))
        return parsed.netloc.replace("www.", "") or clean_text(url)
    except Exception:
        return clean_text(url)


def _extract_response_sources(response: Any) -> List[Dict[str, str]]:
    """Best-effort extraction of web-search citations from Responses outputs."""
    sources: List[Dict[str, str]] = []
    try:
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                for ann in getattr(content, "annotations", []) or []:
                    url = getattr(ann, "url", "") or getattr(ann, "uri", "")
                    title = getattr(ann, "title", "") or _source_domain(url)
                    if url:
                        sources.append({"title": clean_text(title), "url": clean_text(url), "domain": _source_domain(url)})
    except Exception:
        pass
    # Deduplicate while preserving order.
    out: List[Dict[str, str]] = []
    seen = set()
    for src in sources:
        key = src.get("url") or src.get("domain")
        if key and key not in seen:
            seen.add(key)
            out.append(src)
    return out[:8]


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text and text not in ["NA", "nan", "None"]:
            return text
    return ""


def normalize_location_references(profile: Dict[str, Any], limit: int = 8) -> List[Dict[str, str]]:
    """Return clean branch/location rows for the confirmation card.

    Each row is meant for operational targeting: location/city/area plus an
    optional public reference URL. If online evidence is not available, the row
    stays catalog-only and the frontend shows it without a hyperlink.
    """
    refs = profile.get("location_references", [])
    cleaned: List[Dict[str, str]] = []
    seen = set()
    if isinstance(refs, list):
        for item in refs:
            if not isinstance(item, dict):
                continue
            location = _first_nonempty(item.get("location"), item.get("branch"), item.get("name"))
            city = _first_nonempty(item.get("city"), item.get("place"))
            area = _first_nonempty(item.get("area"), item.get("zone"))
            url = clean_text(item.get("source_url") or item.get("url"))
            title = _first_nonempty(item.get("source_title"), item.get("title"), _source_domain(url) if url else "")
            note = _first_nonempty(item.get("note"), item.get("details"))
            key = normalize_key("|".join([location, city, area, url]))
            if key and key not in seen:
                seen.add(key)
                cleaned.append({
                    "location": location or city or area or "Location",
                    "city": city,
                    "area": area,
                    "zone": _first_nonempty(item.get("zone"), area, city),
                    "source_title": title,
                    "source_url": url,
                    "note": note,
                })
            if len(cleaned) >= limit:
                break
    if cleaned:
        return cleaned

    # Catalog-only fallback from parsed list data.
    combined: List[str] = []
    for field in ["branches", "cities", "areas"]:
        vals = profile.get(field, [])
        if isinstance(vals, list):
            combined.extend([clean_text(v) for v in vals if clean_text(v)])
    for loc in combined:
        key = normalize_key(loc)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "location": loc,
            "city": loc if any(x in loc.lower() for x in ["amman", "jordan", "irbid", "zarqa", "aqaba"]) else "",
            "area": "",
            "zone": loc,
            "source_title": "Catalog evidence",
            "source_url": "",
            "note": "Found in internal segmentation catalog.",
        })
        if len(cleaned) >= limit:
            break
    return cleaned


def compact_company_about(profile: Dict[str, Any]) -> str:
    """Very brief About text for grids/exports."""
    company = clean_text(profile.get("company")) or "Company"
    cats = profile.get("category_groups") or []
    if isinstance(cats, str):
        cats = [cats]
    refs = normalize_location_references(profile, limit=4)
    locations = [r.get("location", "") for r in refs if r.get("location")]
    bits = []
    if cats:
        bits.append("Category: " + ", ".join([clean_text(x) for x in cats[:3] if clean_text(x)]))
    if locations:
        bits.append("Locations: " + ", ".join(locations[:4]))
    if profile.get("total_quantity"):
        try:
            bits.append(f"Catalog count: {int(profile.get('total_quantity') or 0):,}")
        except Exception:
            pass
    return f"{company}. " + " | ".join(bits)


def generate_company_about_with_openai(profile: Dict[str, Any], campaign_prompt: str = "", model: str = "gpt-5.5") -> Dict[str, Any]:
    """Compatibility wrapper; company confirmation is catalogue-local only."""
    local_profile = dict(profile)
    local_profile["intelligent_generated"] = False
    return local_profile

def build_company_confirmation(
    df: pd.DataFrame,
    desired_company: str,
    recommended: List[Dict[str, Any]],
    campaign_prompt: str = "",
    use_openai: bool = False,
    model: str = "gpt-5.5",
) -> Dict[str, Any]:
    confirmations = build_company_confirmations(
        df,
        [desired_company] if desired_company not in ["", "Any", "NA"] else [],
        recommended,
        campaign_prompt=campaign_prompt,
        use_openai=use_openai,
        model=model,
    )
    if confirmations:
        return confirmations[0]
    return {"available": False, "company": desired_company or "Any", "about": "No company name was detected in the request."}


def build_company_confirmations(
    df: pd.DataFrame,
    desired_companies: List[str],
    recommended: List[Dict[str, Any]],
    campaign_prompt: str = "",
    use_openai: bool = False,
    model: str = "gpt-5.5",
) -> List[Dict[str, Any]]:
    """Build one confirmation card per detected company.

    Company profiles are generated concurrently because public branch lookups can
    be the slowest part of the request. Results are returned in the original
    detected-company order so the UI remains predictable.
    """
    focus_companies = [clean_text(x) for x in desired_companies if clean_text(x) not in ["", "Any", "NA"]]
    if not focus_companies and recommended:
        for row in recommended:
            company = clean_text(row.get("Company", ""))
            if company and company not in focus_companies:
                focus_companies.append(company)
            if len(focus_companies) >= 3:
                break

    # De-duplicate related lexical matches while preserving order.
    ordered_focus: List[str] = []
    for company in focus_companies[:8]:
        key = normalize_key(company)
        if not key:
            continue
        if any(key in normalize_key(existing) or normalize_key(existing) in key for existing in ordered_focus):
            continue
        ordered_focus.append(company)
        if len(ordered_focus) >= 5:
            break

    def build_one(focus: str) -> Dict[str, Any] | None:
        profile = company_profile_payload(df, focus)
        if not profile.get("available"):
            return None
        profile.setdefault("branches_and_coverage", ", ".join(profile.get("branches", []) + profile.get("cities", []) + profile.get("areas", [])) or "NA")
        profile.setdefault("audience_insights", "; ".join([
            "gender " + "/".join(profile.get("audience_genders", [])) if profile.get("audience_genders") else "",
            "class " + "/".join(profile.get("classes", [])) if profile.get("classes") else "",
            "ages " + "/".join(profile.get("age_ranges", [])) if profile.get("age_ranges") else "",
        ]).strip("; ") or "NA")
        default_why = "The request mentions or implies this company, so matching company/list-owner data is prioritized before broader category lists."
        if profile.get("recommendation_status") and "not ready" in str(profile.get("recommendation_status")).lower():
            default_why += " However, this company appears only in non-ready/stale rows under the current cleaning rules, so final suggestions may use broader matching lists."
        profile.setdefault("why_considered_in_choice", default_why)
        profile.setdefault("confirmation_question", "Confirm the branch/area references before using the suggested lists.")
        profile["location_references"] = normalize_location_references(profile)
        profile["business_category"] = ", ".join(profile.get("category_groups", [])[:3]) or "NA"
        profile["location_selection_guidance"] = "Use listed branches/areas as the first location reference; expand only if target count is low."
        profile["brief_points"] = [profile.get("business_category", "NA"), profile.get("location_selection_guidance", "")]
        profile["about"] = compact_company_about(profile)
        profile["intelligent_generated"] = False
        return profile

    if not ordered_focus:
        return []
    if not use_openai or len(ordered_focus) == 1:
        return [p for p in (build_one(focus) for focus in ordered_focus) if p]

    results_by_company: Dict[str, Dict[str, Any]] = {}
    max_workers = min(len(ordered_focus), int(os.getenv("ABOUT_MAX_WORKERS", "4") or 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(build_one, focus): focus for focus in ordered_focus}
        for future in as_completed(future_map):
            focus = future_map[future]
            try:
                profile = future.result()
                if profile:
                    results_by_company[focus] = profile
            except Exception as exc:
                fallback = company_profile_payload(df, focus)
                if fallback.get("available"):
                    fallback["profile_enrichment_error"] = str(exc)
                    fallback["location_references"] = normalize_location_references(fallback)
                    fallback["about"] = compact_company_about(fallback)
                    results_by_company[focus] = fallback
    return [results_by_company[focus] for focus in ordered_focus if focus in results_by_company]


def load_segments(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    sep = "," if path.suffix.lower() == ".csv" else "\t"
    raw = pd.read_csv(path, sep=sep, header=None, names=[0, 1, 2, 3], dtype=str, keep_default_na=False, engine="python")
    if len(raw) and clean_text(raw.iloc[0, 0]).lower() == "check":
        raw = raw.iloc[1:].copy()

    df = raw.iloc[:, :4].copy()
    df.columns = ["Check", "Raw List", "Quantity", "Needed Quantity"]
    df = df[df["Raw List"].map(clean_text) != ""].copy().reset_index(drop=True)
    for col in ["Check", "Raw List", "Quantity", "Needed Quantity"]:
        df[col] = df[col].map(clean_text)
    df["Quantity"] = df["Quantity"].map(to_int_safe)
    df["Needed Quantity"] = df["Needed Quantity"].map(to_int_safe)
    df["Count OK"] = df["Quantity"] == df["Needed Quantity"]
    df["Checked"] = df["Check"].str.lower().isin(["true", "yes", "1", "y"])

    parsed = pd.DataFrame([parse_segment_text(x) for x in df["Raw List"]])
    out = pd.concat([df, parsed], axis=1)

    out["Source Exclusion Reason"] = out.apply(
        lambda r: source_exclusion_reason(
            r.get("Raw List", ""), r.get("List Name", ""), r.get("Company", ""), r.get("Original Category", ""), r.get("Category", "")
        ),
        axis=1,
    )
    out["Source Eligible"] = out["Source Exclusion Reason"].astype(str).str.startswith("Keep")

    out["Staleness Rule"] = out.apply(
        lambda r: "Keep - special list" if r["Unique / Special List"] else (
            "Keep - recent" if pd.notna(r["Created Year"]) and int(r["Created Year"]) >= MIN_KEEP_YEAR else "Drop - older than 2020"
        ),
        axis=1,
    )
    out["Keep After Date Rule"] = out["Staleness Rule"].str.startswith("Keep")

    # Operational duplicate logic:
    # - Exact duplicate except date = same profiling AND same quantity, only creation date differs.
    # - Profile duplicate = same profiling, quantity may differ. The recommender will prefer only one profile.
    profile_cols = ["Company", "Location Hint", "Gender", "Class", "Age Range", "Category", "City / Coverage", "Area", "Unique / Special List"]
    exact_cols = profile_cols + ["Quantity"]
    out["Profile Key Except Date"] = out[profile_cols].apply(lambda r: " | ".join(normalize_key(x) for x in r), axis=1)
    out["Duplicate Key Except Date"] = out[exact_cols].apply(lambda r: " | ".join(normalize_key(x) for x in r), axis=1)
    out["Duplicate Group Size"] = out.groupby("Duplicate Key Except Date")["Duplicate Key Except Date"].transform("size")
    out["Profile Duplicate Group Size"] = out.groupby("Profile Key Except Date")["Profile Key Except Date"].transform("size")
    out["Duplicate Except Date"] = out["Duplicate Group Size"] > 1
    out["Same Profile Multiple Dates"] = out["Profile Duplicate Group Size"] > 1

    out["_date_rank"] = pd.to_datetime(out["Created Date"], errors="coerce").fillna(pd.Timestamp("1900-01-01"))
    out["_quantity_rank"] = pd.to_numeric(out["Quantity"], errors="coerce").fillna(0)
    preferred_idx = (
        out.sort_values(["Duplicate Key Except Date", "_date_rank", "_quantity_rank"], ascending=[True, False, False])
        .groupby("Duplicate Key Except Date", dropna=False)
        .head(1)
        .index
    )
    most_unique_idx = (
        out.sort_values(["Profile Key Except Date", "_date_rank", "_quantity_rank"], ascending=[True, False, False])
        .groupby("Profile Key Except Date", dropna=False)
        .head(1)
        .index
    )
    out["Preferred Duplicate Version"] = False
    out.loc[preferred_idx, "Preferred Duplicate Version"] = True
    out["Most Unique Profile Version"] = False
    out.loc[most_unique_idx, "Most Unique Profile Version"] = True

    out["Ready for Recommendation"] = out["Checked"] & out["Count OK"] & out["Keep After Date Rule"] & out["Source Eligible"] & out["Preferred Duplicate Version"]

    # Local company profile summary used in the UI and exports. OpenAI can enhance
    # the confirmation card per request, but the catalog always has a safe local About column.
    out = add_company_about_column(out)

    friendly_order = [
        "List ID", "List Name", "Company", "About", "Category", "Business Category Group", "Original Category",
        "Gender", "Class", "Age Range", "City / Coverage", "Area", "Quantity", "Created Date",
        "Unique / Special List", "Exclusive Data", "Ready for Recommendation", "Duplicate Except Date", "Preferred Duplicate Version",
        "Same Profile Multiple Dates", "Most Unique Profile Version", "Profile Duplicate Group Size",
        "Source Eligible", "Source Exclusion Reason", "Staleness Rule", "Count OK", "Checked", "Needed Quantity",
    ]
    return out[friendly_order + [c for c in out.columns if c not in friendly_order and not c.startswith("_")]].copy()


def load_cached_segments(source_path: Path, cache_path: Path, force: bool = False) -> pd.DataFrame:
    """Load a preprocessed catalog so the app does not parse the TSV on every run.

    The package includes data/processed_segments.csv. If that file exists, it is
    loaded directly. If it is missing or force=True, the TSV is parsed once and
    the processed CSV is recreated.
    """
    if cache_path.exists() and not force:
        df = pd.read_csv(cache_path, dtype={"List ID": str}, keep_default_na=False)
        # Rebuild older caches that do not yet include clustered categories.
        if (
            "Business Category Group" not in df.columns
            or "Original Category" not in df.columns
            or "Exclusive Data" not in df.columns
            or "About" not in df.columns
            or "Source Eligible" not in df.columns
            or "Source Exclusion Reason" not in df.columns
        ):
            return load_cached_segments(source_path, cache_path, force=True)
        # Restore common boolean columns saved in CSV.
        bool_cols = [
            "Unique / Special List", "Ready for Recommendation", "Duplicate Except Date",
            "Preferred Duplicate Version", "Same Profile Multiple Dates", "Most Unique Profile Version",
            "Count OK", "Checked", "Exclusive Data", "Source Eligible",
        ]
        for col in bool_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])
        for col in ["Quantity", "Needed Quantity", "Created Year", "Duplicate Group Size", "Profile Duplicate Group Size"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df

    df = load_segments(source_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return df


def build_filter_options(df: pd.DataFrame) -> Dict[str, Any]:
    def options(col: str, limit: int = 200) -> List[str]:
        values = df.loc[df["Ready for Recommendation"], col].fillna("NA").astype(str)
        cleaned = []
        for v in values.value_counts().head(limit * 2).index.tolist():
            v = clean_text(v)
            if not v or v == "nan":
                continue
            # Prevent broken parse artifacts from appearing as business categories.
            if col == "Category" and re.search(r"\(\d{1,2}/\d{1,2}/\d{4}\)", v):
                continue
            cleaned.append(v)
        return ["Any"] + sorted(cleaned[:limit])

    ready = df[df["Ready for Recommendation"]].copy()
    mins, maxs = [], []
    for age in ready.get("Age Range", pd.Series(dtype=str)).dropna().astype(str):
        lo, hi = parse_age_bounds(age)
        if lo is not None and hi is not None and 0 < lo <= 100 and 0 < hi <= 100:
            mins.append(lo)
            maxs.append(hi)
    age_min = int(min(mins)) if mins else 17
    age_max = int(max(maxs)) if maxs else 80

    return {
        "categories": options("Category"),
        "genders": ["Any", "Mixed", "Male", "Female", "NA"],
        "classes": options("Class"),
        "ages": options("Age Range"),
        "age_bounds": {"min": age_min, "max": age_max},
        "cities": options("City / Coverage"),
        "areas": options("Area"),
        # Company options are internal for lexical prompt detection. Include all companies, even stale ones,
        # so a mentioned company can still be recognized and shown in the confirmation card.
        "companies": ["Any"] + sorted([v for v in df["Company"].fillna("NA").astype(str).map(clean_text).unique().tolist() if v and v not in ["Any", "nan"]]),
    }



def infer_company_from_prompt(prompt: str, companies: Iterable[str]) -> str:
    """Detect an explicit company/list owner mentioned in the request lexically.

    This is used only for prioritization. It does not create new demographic data.
    """
    if not clean_text(prompt):
        return "Any"
    best = "Any"
    best_score = 0
    best_len = 0
    for company in companies:
        c = clean_text(company)
        if c in ["", "Any", "NA", "nan"]:
            continue
        if not lexical_tokens(c):
            continue
        score = lexical_company_score(prompt, c)
        c_len = len(normalize_key(c))
        if score > best_score or (score == best_score and c_len > best_len):
            best = c
            best_score = score
            best_len = c_len
    return best if best_score >= 58 else "Any"


def _prompt_company_terms(prompt: str) -> List[str]:
    """Extract non-generic prompt terms/phrases useful for company matching."""
    raw_tokens = re.findall(r"[0-9a-zA-Z\u0600-\u06FF]+", clean_text(prompt).lower())
    tokens = [t for t in raw_tokens if len(t) >= 3 and t not in STOPWORDS]
    terms: List[str] = []
    # Include single distinctive tokens plus adjacent bi/tri-grams from the raw text.
    for t in tokens:
        if t not in terms:
            terms.append(t)
    for n in [2, 3]:
        for i in range(len(raw_tokens) - n + 1):
            phrase_tokens = raw_tokens[i:i+n]
            if any(t in STOPWORDS for t in phrase_tokens):
                # Keep phrases only when they look like an explicit proper/common brand phrase.
                phrase = " ".join(phrase_tokens)
                if phrase not in normalize_key(prompt):
                    continue
            phrase = " ".join(phrase_tokens)
            if len(phrase) >= 5 and phrase not in terms:
                terms.append(phrase)
    return terms[:40]


def infer_companies_from_prompt(prompt: str, companies: Iterable[str], limit: int = 5) -> List[str]:
    """Detect one or more company/list owners mentioned in the request.

    The app can receive requests such as "send to Toyota and City Mall". This
    returns all strong lexical matches, ordered by score and name length, so the
    recommender prioritizes each detected company before broader category lists.
    """
    if not clean_text(prompt):
        return []
    # When the whole prompt is a generic audience request, do not treat matching
    # audience/list labels as explicit company names. Example: "all university
    # students" is an audience, not a company called "University students".
    prompt_is_generic_audience = is_audience_only_phrase(prompt)
    if prompt_is_generic_audience:
        return []
    prompt_terms = _prompt_company_terms(prompt)
    scored: List[Tuple[int, int, str]] = []
    for company in companies:
        c = clean_text(company)
        if c in ["", "Any", "NA", "nan"]:
            continue
        if prompt_is_generic_audience and is_audience_only_phrase(c):
            continue
        company_words = re.findall(r"[0-9a-zA-Z؀-ۿ]+", normalize_key(c))
        # Avoid geographic/generic one-word company artifacts such as "Amman".
        if not lexical_tokens(c) and len(company_words) < 2:
            continue
        # Exact phrase match should work even if tokens like city/mall are generic.
        full_score = lexical_company_score(prompt, c)
        term_score = max([lexical_company_score(term, c) for term in prompt_terms] or [0])
        score = max(full_score, term_score)
        if score >= 58:
            scored.append((score, len(normalize_key(c)), c))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    output: List[str] = []
    seen = set()
    for score, _length, company in scored:
        key = normalize_key(company)
        if key in seen:
            continue
        if any(key in normalize_key(existing) or normalize_key(existing) in key for existing in output):
            continue
        output.append(company)
        seen.add(key)
        if len(output) >= limit:
            break
    return output

def infer_category_from_prompt(prompt: str, categories: Iterable[str]) -> str:
    p = clean_text(prompt).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k.lower() in p for k in keywords):
            return category
    # Fallback: category name token in prompt.
    for cat in categories:
        if cat and cat != "Any" and cat.lower() in p:
            return cat
    return "Any"


def filter_from_prompt_heuristic(prompt: str, options: Dict[str, List[str]]) -> Dict[str, Any]:
    p = clean_text(prompt).lower()
    product_intent = infer_product_industry_intent(prompt)
    # Product intent always clears company matches below. Resolve it first so a
    # product-only request does not pay for a full fuzzy company scan whose
    # result would be discarded without affecting legacy output.
    detected_companies = [] if product_intent else infer_companies_from_prompt(prompt, options.get("companies", []))
    result = {
        "desired_company": detected_companies[0] if detected_companies else "Any",
        "desired_companies": detected_companies,
        "desired_category": infer_category_from_prompt(prompt, options.get("categories", [])),
        "desired_gender": "Any",
        "desired_socioeconomic_class": "Any",
        "desired_age_range": "Any",
        "desired_city": "Any",
        "desired_area": "Any",
        "must_have_keywords": [],
        "avoid_keywords": [],
        "strict_category_match": False,
        "strict_logical_match": False,
        "audience_intent": "",
        "logical_intent": "",
        "allow_class_downgrade": True,
        "allow_age_extension": True,
        "use_allclasses_only_as_backup": True,
        "reasoning_summary": "Used deterministic keyword matching from the campaign prompt.",
    }

    if product_intent:
        # Product/industry requests are not company-name requests unless an
        # actual company is explicitly detected by a strong proper phrase.
        result.update(product_intent)
        result["desired_company"] = "Any"
        result["desired_companies"] = []

    if has_strong_education_intent(prompt):
        result["desired_category"] = "Education & Students"
        result["strict_category_match"] = True
        if "university" in p or "universities" in p or "college" in p:
            result["audience_intent"] = "University students"
            result["must_have_keywords"] = ["university", "universities", "college", "graduate", "graduates", "tawjihi"]
        elif "tawjihi" in p:
            result["audience_intent"] = "Tawjihi students"
            result["must_have_keywords"] = ["tawjihi", "students", "student", "graduates"]
        elif "school" in p or "schools" in p:
            result["audience_intent"] = "Schools / students"
            result["must_have_keywords"] = ["school", "schools", "students", "student", "parents"]
        else:
            result["audience_intent"] = "Education / students"
            result["must_have_keywords"] = ["student", "students", "university", "universities", "graduates", "tawjihi", "school", "education"]
        if is_audience_only_phrase(prompt):
            result["desired_company"] = "Any"
            result["desired_companies"] = []

    if any(x in p for x in ["female", "women", "ladies", "نسائي", "نساء"]):
        result["desired_gender"] = "Female"
    elif any(x in p for x in ["male", "men", "رجالي", "رجال"]):
        result["desired_gender"] = "Male"

    # Match longer class names first so "Economy Plus" is not reduced to "Economy".
    for cls in sorted(options.get("classes", []), key=len, reverse=True):
        if cls != "Any" and cls.lower() in p:
            result["desired_socioeconomic_class"] = cls
            break

    m_age = re.search(r"(\d{2})\s*(?:-|to|الى|إلى)\s*(\d{2})", p)
    if m_age:
        result["desired_age_range"] = normalize_age_range(f"{m_age.group(1)} - {m_age.group(2)}")

    for city in options.get("cities", []):
        if city != "Any" and city.lower() in p:
            result["desired_city"] = city
            break
    if "west" in p or "غرب" in p:
        result["desired_city"] = "Amman - West"
    elif "east" in p or "شرق" in p:
        result["desired_city"] = "Amman - East"

    company_text = " ".join(result.get("desired_companies", []))
    for area in options.get("areas", [])[:200]:
        area_clean = clean_text(area)
        if area_clean in ["Any", "NA"] or len(area_clean) < 3:
            continue
        # Do not confuse a company token with an area value.
        if company_text and normalize_key(area_clean) in normalize_key(company_text):
            continue
        if result.get("strict_category_match") and normalize_key(area_clean) in EDUCATION_INTENT_TERMS:
            continue
        if area_clean.lower() in p:
            result["desired_area"] = area_clean
            break

    return result


def _extract_response_text(response: Any) -> str:
    """Return text from the most common OpenAI SDK response shapes."""
    text = getattr(response, "output_text", "") or ""
    if text:
        return text
    try:
        return response.output[0].content[0].text
    except Exception:
        pass
    try:
        return response.choices[0].message.content
    except Exception:
        pass
    return "{}"


def _validate_campaign_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing keys so the UI never breaks if the model returns partial JSON."""
    defaults = {
        "desired_company": "Any",
        "desired_companies": [],
        "desired_category": "Any",
        "desired_gender": "Any",
        "desired_socioeconomic_class": "Any",
        "desired_age_range": "Any",
        "desired_city": "Any",
        "desired_area": "Any",
        "must_have_keywords": [],
        "avoid_keywords": [],
        "strict_category_match": False,
        "strict_logical_match": False,
        "audience_intent": "",
        "logical_intent": "",
        "allow_class_downgrade": True,
        "allow_age_extension": True,
        "use_allclasses_only_as_backup": True,
        "reasoning_summary": "OpenAI interpreted the request.",
    }
    if not isinstance(payload, dict):
        payload = {}
    merged = {**defaults, **payload}
    for key in ["must_have_keywords", "avoid_keywords", "desired_companies"]:
        if not isinstance(merged.get(key), list):
            merged[key] = []
    # Keep the legacy single-company field synchronized with the list field.
    if merged.get("desired_company") not in ["", "Any", "NA", None] and not merged.get("desired_companies"):
        merged["desired_companies"] = [clean_text(merged.get("desired_company"))]
    merged["desired_companies"] = [clean_text(x) for x in merged.get("desired_companies", []) if clean_text(x) and clean_text(x) not in ["Any", "NA"]]
    if merged.get("desired_companies"):
        merged["desired_company"] = merged["desired_companies"][0]
    for key in ["allow_class_downgrade", "allow_age_extension", "use_allclasses_only_as_backup", "strict_category_match", "strict_logical_match"]:
        merged[key] = bool(merged.get(key))
    return merged



def _option_values(options: Dict[str, Any], key: str) -> List[str]:
    values = options.get(key, []) or []
    return [clean_text(v) for v in values if clean_text(v)]


def _canonical_option(value: Any, values: Iterable[str], default: str = "Any") -> str:
    """Map an OpenAI/local suggestion to the closest available dropdown value.

    The model is allowed to reason in natural language, but filtering must be
    applied only through the real filter options that exist in the cleaned data.
    """
    raw = clean_text(value)
    if raw in ["", "Any", "NA", "Unknown", "None"]:
        return default
    choices = [clean_text(v) for v in values if clean_text(v)]
    if not choices:
        return raw if raw else default
    raw_key = normalize_key(raw)
    for c in choices:
        if normalize_key(c) == raw_key:
            return c
    # Use careful containment only for meaningful phrases to avoid mapping
    # short words like "men" into unrelated labels.
    if len(raw_key) >= 5:
        for c in choices:
            ck = normalize_key(c)
            if raw_key in ck or ck in raw_key:
                return c
    return default



def _canonical_options(value: Any, values: Iterable[str], default: str = "Any") -> Any:
    """Canonicalize a single suggested value or a list of suggested values."""
    if isinstance(value, list):
        mapped: List[str] = []
        for item in value:
            m = _canonical_option(item, values, default)
            if m not in ["", default, "NA"] and m not in mapped:
                mapped.append(m)
        return mapped if mapped else default
    return _canonical_option(value, values, default)


def canonicalize_campaign_filters(filters: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    """Validate GPT/local filter suggestions against real UI dropdown options."""
    out = _validate_campaign_payload(filters)
    company_values = _option_values(options, "companies")
    company_guesses = [clean_text(x) for x in out.get("desired_companies", []) if clean_text(x)]
    legacy_company = clean_text(out.get("desired_company", "Any"))
    if legacy_company not in ["", "Any", "NA", "Unknown", "None"] and legacy_company not in company_guesses:
        company_guesses.insert(0, legacy_company)
    canonical_companies: List[str] = []
    for guess in company_guesses:
        mapped = _canonical_option(guess, company_values, "Any")
        if mapped == "Any" and guess not in ["", "Any", "NA", "Unknown", "None"]:
            mapped = guess
        if mapped not in ["", "Any", "NA"] and mapped not in canonical_companies:
            canonical_companies.append(mapped)
    out["desired_companies"] = canonical_companies
    out["desired_company"] = canonical_companies[0] if canonical_companies else "Any"
    out["desired_category"] = _canonical_options(out.get("desired_category"), _option_values(options, "categories"), "Any")
    out["desired_gender"] = _canonical_option(out.get("desired_gender"), ["Any", "Mixed", "Male", "Female", "NA"], "Any")
    out["desired_socioeconomic_class"] = _canonical_option(out.get("desired_socioeconomic_class"), _option_values(options, "classes"), "Any")
    out["desired_city"] = _canonical_option(out.get("desired_city"), _option_values(options, "cities"), "Any")
    out["desired_area"] = _canonical_option(out.get("desired_area"), _option_values(options, "areas"), "Any")

    suggested_age = clean_text(out.get("desired_age_range", "Any"))
    if suggested_age not in ["", "Any", "NA"]:
        normalized_age = normalize_age_range(suggested_age)
        out["desired_age_range"] = normalized_age if normalized_age != "NA" else _canonical_option(suggested_age, _option_values(options, "ages"), "Any")
    else:
        out["desired_age_range"] = "Any"
    return out

def interpret_campaign_with_openai(prompt: str, options: Dict[str, List[str]], model: str = "gpt-5.5") -> Dict[str, Any]:
    """Compatibility wrapper; legacy filter interpretation remains local-only."""
    local = filter_from_prompt_heuristic(prompt, options)
    return canonicalize_campaign_filters(local, options)


def _clean_filter_item(value: Any) -> str:
    text = clean_text(value)
    return text if text else "Any"


def user_value(payload: Dict[str, Any], key: str, default: str = "Any") -> str:
    value = payload.get(key, default)
    if isinstance(value, list):
        values = [clean_text(v) for v in value if clean_text(v) and clean_text(v) not in ["Any", "NA"]]
        return values[0] if values else default
    value = clean_text(value)
    return value if value else default


def user_values(payload: Dict[str, Any], *keys: str) -> List[str]:
    """Return multi-select values for one or more possible payload keys.

    The UI now sends dropdown fields as tag arrays. OpenAI/local interpretation
    can still provide a single string. This helper normalizes both into a clean
    list and removes Any/blank values.
    """
    output: List[str] = []
    for key in keys:
        value = payload.get(key, "Any")
        if isinstance(value, list):
            raw_values = value
        else:
            raw_values = [value]
        for item in raw_values:
            text = clean_text(item)
            if not text or text in ["Any", "NA", "None", "Unknown"]:
                continue
            if text not in output:
                output.append(text)
    return output


def join_filter_values(values: Iterable[Any]) -> str:
    cleaned = [clean_text(v) for v in values if clean_text(v) and clean_text(v) not in ["Any", "NA"]]
    return ", ".join(dict.fromkeys(cleaned)) if cleaned else "Any"


def class_match(row_class: str, requested: str, allow_downgrade: bool, use_allclasses_backup: bool) -> Tuple[bool, int, str]:
    rc = clean_text(row_class) or "NA"
    req = clean_text(requested) or "Any"
    if req in ["Any", "NA", ""]:
        if use_allclasses_backup and rc == "AllClasses":
            return True, -6, "Broad class backup"
        return True, 0, "No class filter"
    if rc == req:
        return True, 22, "Exact class match"
    if rc == "AllClasses":
        return True, -12 if use_allclasses_backup else -2, "AllClasses backup only"
    if allow_downgrade and rc in CLASS_DOWNGRADE_CHAIN.get(req, []):
        return True, 7, f"Class downgrade backup from {req} to {rc}"
    return False, -50, "Class mismatch"


def gender_match(row_gender: str, requested: str) -> Tuple[bool, int, str]:
    rg = clean_text(row_gender) or "NA"
    req = clean_text(requested) or "Any"
    if req in ["Any", "NA", ""]:
        return True, 0, "No gender filter"
    if rg == req:
        return True, 15, "Exact gender match"
    if rg == "Mixed":
        return True, 3, "Mixed gender backup"
    return False, -40, "Gender mismatch"


def age_match(row_age: str, requested: str, allow_extension: bool) -> Tuple[bool, int, str]:
    ra = clean_text(row_age) or "NA"
    req = clean_text(requested) or "Any"
    if req in ["Any", "NA", ""]:
        return True, 0, "No age filter"
    if normalize_age_range(ra) == normalize_age_range(req):
        return True, 18, "Exact age range"
    if allow_extension and range_contains(ra, req):
        return True, 8, f"Extended age range backup: {ra} contains {req}"
    if allow_extension and ranges_overlap(ra, req):
        return True, 2, f"Partial age overlap backup: {ra} overlaps {req}"
    return False, -45, "Age mismatch"


def best_match_from_many(match_func, row_value: str, requested_values: Iterable[str], *args) -> Tuple[bool, int, str, str]:
    """Pick the best match against any selected tag value.

    Returns (ok, score_delta, reason, selected_value). Empty requested_values means
    no filter. This keeps multi-select dropdowns as OR filters.
    """
    values = [clean_text(v) for v in requested_values if clean_text(v) and clean_text(v) not in ["Any", "NA"]]
    if not values:
        ok, add, reason = match_func(row_value, "Any", *args)
        return ok, add, reason, "Any"
    results = []
    for req in values:
        ok, add, reason = match_func(row_value, req, *args)
        results.append((ok, add, reason, req))
    # Prefer valid matches; within validity, choose the highest score. If all
    # fail, return the least-bad result for a clear explanation.
    results.sort(key=lambda x: (bool(x[0]), int(x[1])), reverse=True)
    return results[0]


def category_match(row_category: str, requested_values: Iterable[str], strict: bool, company_priority_match: bool) -> Tuple[bool, int, List[str], List[str], bool]:
    """Match a row category against one or more selected category tags.

    Returns (ok_or_soft_ok, score_delta, reasons, match_type_parts, hard_fail).
    """
    values = [clean_text(v) for v in requested_values if clean_text(v) and clean_text(v) not in ["Any", "NA"]]
    if not values:
        return True, 0, [], [], False
    row_key = normalize_key(row_category)
    best: Tuple[int, str, str] | None = None
    for desired in values:
        desired_key = normalize_key(desired)
        if row_key == desired_key:
            candidate = (25, f"Exact category match: {desired}", f"Exact category: {desired}")
        elif desired_key and (desired_key in row_key or row_key in desired_key):
            candidate = (10, f"Related category match: {desired}", f"Related category: {desired}")
        else:
            continue
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is not None:
        return True, best[0], [best[1]], [best[2]], False
    if strict:
        return False, 0, ["Strict audience/category mismatch"], [], True
    if company_priority_match:
        return True, -12, ["Category mismatch, but kept because company name matches lexically"], ["Company-first relaxed category"], False
    return False, 0, ["Category mismatch"], [], True


def simple_multi_value_match(row_value: str, requested_values: Iterable[str], label: str, exact_score: int, related_score: int = 6, allow_na_backup: bool = False) -> Tuple[bool, int, str, str]:
    values = [clean_text(v) for v in requested_values if clean_text(v) and clean_text(v) not in ["Any", "NA"]]
    if not values:
        return True, 0, f"No {label.lower()} filter", "Any"
    rv = clean_text(row_value) or "NA"
    rv_key = normalize_key(rv)
    best: Tuple[bool, int, str, str] | None = None
    for req in values:
        req_key = normalize_key(req)
        if rv_key == req_key:
            candidate = (True, exact_score, f"Exact {label.lower()} match: {req}", req)
        elif req_key and (req_key in rv_key or rv_key in req_key):
            candidate = (True, related_score, f"Related {label.lower()} match: {req}", req)
        elif allow_na_backup and rv in ["NA", "All Over Jordan"]:
            candidate = (True, -3, f"{label} unavailable/broad backup", req)
        else:
            candidate = (False, -30, f"{label} mismatch", req)
        if best is None or (candidate[0], candidate[1]) > (best[0], best[1]):
            best = candidate
    return best or (False, -30, f"{label} mismatch", "")


def text_contains_any(text: str, keywords: Iterable[str]) -> bool:
    low = clean_text(text).lower()
    return any(clean_text(k).lower() in low for k in keywords if clean_text(k))



def _target_gap(selection: pd.DataFrame, target_quantity: int) -> int:
    if selection is None or selection.empty:
        return int(target_quantity or 0)
    return abs(int(selection["Quantity"].sum()) - int(target_quantity or 0))


def _backup_weight(selection: pd.DataFrame) -> int:
    if selection is None or selection.empty:
        return 0
    text = (selection.get("Match Type", pd.Series(dtype=str)).astype(str) + " " + selection.get("Why Recommended", pd.Series(dtype=str)).astype(str)).str.lower()
    return int(text.str.contains("backup|allclasses|downgrade|extended age|partial age|broad", regex=True, na=False).sum())


def _selection_sort_key(selection: pd.DataFrame, target_quantity: int) -> Tuple[int, int, int, float, int]:
    """Rank candidate selections for target delivery.

    Target count is treated as a minimum delivery goal. A selection that reaches
    the target is always preferred over one that is slightly closer but still
    below target. Among reached selections, prefer the smallest overshoot, then
    fewer backup/broad lists, then stronger relevance.
    """
    if selection is None or selection.empty:
        return (1, int(target_quantity or 0), 9999, 999999.0, 9999)
    target_quantity = int(target_quantity or 0)
    total = int(pd.to_numeric(selection["Quantity"], errors="coerce").fillna(0).sum())
    if target_quantity <= 0:
        target_rank = 0
        count_gap = 0
    elif total >= target_quantity:
        target_rank = 0
        count_gap = total - target_quantity
    else:
        target_rank = 1
        count_gap = target_quantity - total
    backup = _backup_weight(selection)
    avg_score = float(pd.to_numeric(selection["Recommendation Score"], errors="coerce").fillna(0).mean())
    # smaller tuple is better: reached target, smaller over/short amount, fewer backups, higher score, fewer lists
    return (target_rank, count_gap, backup, -avg_score, int(len(selection)))


def _target_aware_select(pool: pd.DataFrame, max_lists: int, target_quantity: int) -> pd.DataFrame:
    """Select lists to reach the target count whenever possible.

    The target is now a minimum delivery goal, not only a "closest count" display.
    The selector first tries to reach the target with the best-ranked unique lists.
    If the preferred maximum-list count is too small, it automatically expands
    within the already-approved filtered pool until the target is reached or no
    more suitable rows are available.
    """
    if pool is None or pool.empty:
        return pd.DataFrame()
    preferred_max_lists = max(1, int(max_lists or DEFAULT_MAX_LISTS))
    target_quantity = int(target_quantity or 0)
    # For target delivery, the UI maximum is treated as the preferred list count.
    # If it cannot reach the target, the engine may add more approved lists.
    # Keep a high but finite safety cap so a mistaken huge target cannot flood the browser.
    target_expand_limit = len(pool) if preferred_max_lists >= 9999 else min(len(pool), max(preferred_max_lists, 500))
    max_lists = preferred_max_lists
    sorted_pool = pool.sort_values(
        ["Recommendation Score", "Exclusive Data", "Most Unique Profile Version", "Profile Duplicate Group Size", "Created Date", "Quantity"],
        ascending=[False, False, False, True, False, False],
    ).copy()
    if target_quantity <= 0:
        return sorted_pool.head(max_lists).copy()

    candidates = sorted_pool.head(max(800, target_expand_limit)).copy()
    strategies: List[pd.DataFrame] = []

    def add_candidate(sel: pd.DataFrame):
        if sel is not None and not sel.empty:
            sel = sel.drop_duplicates("List ID").head(max_lists).copy()
            if not sel.empty:
                strategies.append(sel)

    # 1) Prefixes by relevance: preserves the most suitable ordering.
    top = candidates.head(max_lists)
    for k in range(1, min(max_lists, len(top)) + 1):
        add_candidate(top.head(k))

    # 2) Best single-list and quantity-oriented prefixes.
    qty_sorted = candidates.assign(_qty_gap=(pd.to_numeric(candidates["Quantity"], errors="coerce").fillna(0) - target_quantity).abs())
    qty_sorted = qty_sorted.sort_values(["_qty_gap", "Recommendation Score"], ascending=[True, False]).drop(columns=["_qty_gap"])
    for k in range(1, min(max_lists, len(qty_sorted)) + 1):
        add_candidate(qty_sorted.head(k))

    # 3) Greedy closeness: repeatedly add the row that most improves closeness.
    remaining = candidates.copy()
    chosen_rows = []
    current_total = 0
    while len(chosen_rows) < max_lists and not remaining.empty:
        tmp = remaining.copy()
        tmp["_new_gap"] = (current_total + pd.to_numeric(tmp["Quantity"], errors="coerce").fillna(0).astype(int) - target_quantity).abs()
        tmp["_new_total"] = current_total + pd.to_numeric(tmp["Quantity"], errors="coerce").fillna(0).astype(int)
        tmp = tmp.sort_values(["_new_gap", "Recommendation Score", "Quantity"], ascending=[True, False, False])
        pick = tmp.iloc[0]
        chosen_rows.append(pick.drop(labels=[c for c in ["_new_gap", "_new_total"] if c in pick.index]).to_dict())
        current_total += int(pick["Quantity"])
        remaining = remaining[remaining["List ID"] != pick["List ID"]]
        add_candidate(pd.DataFrame(chosen_rows))
        # If we passed target and the gap is already small, keep strategy but continue
        # only if there are more slots; another small list may or may not improve.

    # 4) Under-target fill: prefer high relevance while avoiding unnecessary overshoot.
    remaining = candidates.copy()
    chosen = pd.DataFrame()
    current_total = 0
    while len(chosen) < max_lists and not remaining.empty:
        under = remaining[pd.to_numeric(remaining["Quantity"], errors="coerce").fillna(0).astype(int) <= max(0, target_quantity - current_total)]
        if under.empty:
            # pick the smallest overshoot among the strongest remaining lists
            tmp = remaining.copy()
            tmp["_overshoot_gap"] = (current_total + pd.to_numeric(tmp["Quantity"], errors="coerce").fillna(0).astype(int) - target_quantity).abs()
            pick_df = tmp.sort_values(["_overshoot_gap", "Recommendation Score"], ascending=[True, False]).head(1).drop(columns=["_overshoot_gap"])
        else:
            pick_df = under.sort_values(["Recommendation Score", "Quantity"], ascending=[False, False]).head(1)
        chosen = pd.concat([chosen, pick_df], ignore_index=True)
        current_total = int(pd.to_numeric(chosen["Quantity"], errors="coerce").fillna(0).sum())
        remaining = remaining[~remaining["List ID"].isin(set(chosen["List ID"]))]
        add_candidate(chosen)
        if current_total >= target_quantity:
            break

    best = min(strategies, key=lambda sel: _selection_sort_key(sel, target_quantity)) if strategies else sorted_pool.head(max_lists)

    # Auto-expand when the preferred maximum-list count is not enough to reach
    # the target. This only adds rows from the already-filtered, scored, unique
    # recommendation pool, so strict logical audience/category rules still hold.
    best = best.drop_duplicates("List ID").copy()
    current_total = int(pd.to_numeric(best["Quantity"], errors="coerce").fillna(0).sum())
    if target_quantity > 0 and current_total < target_quantity and len(best) < target_expand_limit:
        remaining = sorted_pool[~sorted_pool["List ID"].isin(set(best["List ID"]))].copy()
        while current_total < target_quantity and len(best) < target_expand_limit and not remaining.empty:
            tmp = remaining.copy()
            qty = pd.to_numeric(tmp["Quantity"], errors="coerce").fillna(0).astype(int)
            tmp["_target_rank"] = (current_total + qty < target_quantity).astype(int)
            tmp["_target_gap"] = (current_total + qty - target_quantity).abs()
            tmp["_backup"] = (
                tmp.get("Match Type", pd.Series(dtype=str)).astype(str).str.lower() + " " +
                tmp.get("Why Recommended", pd.Series(dtype=str)).astype(str).str.lower()
            ).str.contains("backup|allclasses|downgrade|extended age|partial age|broad", regex=True, na=False).astype(int)
            pick_df = tmp.sort_values(
                ["_target_rank", "_target_gap", "_backup", "Recommendation Score", "Quantity"],
                ascending=[True, True, True, False, False],
            ).head(1).drop(columns=["_target_rank", "_target_gap", "_backup"], errors="ignore")
            best = pd.concat([best, pick_df], ignore_index=True)
            current_total = int(pd.to_numeric(best["Quantity"], errors="coerce").fillna(0).sum())
            remaining = remaining[~remaining["List ID"].isin(set(best["List ID"]))]

    return best.drop(columns=[c for c in best.columns if c.startswith("_")], errors="ignore").copy()

def recommend_lists(
    df: pd.DataFrame,
    filters: Dict[str, Any],
    max_lists: int = DEFAULT_MAX_LISTS,
    min_quantity: int = DEFAULT_MIN_QUANTITY,
    target_quantity: int = 0,
    enhance_count: bool = False,
    include_unique_lists: bool = True,
    allow_class_downgrade: bool = True,
    allow_age_extension: bool = True,
    use_allclasses_only_as_backup: bool = True,
) -> Dict[str, Any]:
    catalog = df[df["Ready for Recommendation"]].copy()
    if not include_unique_lists:
        catalog = catalog[~catalog["Unique / Special List"]]
    if min_quantity:
        catalog = catalog[catalog["Quantity"] >= int(min_quantity)]

    desired_companies = [clean_text(x) for x in (filters.get("desired_companies") or []) if clean_text(x) not in ["", "Any", "NA"]]
    legacy_desired_company = user_value(filters, "company", user_value(filters, "desired_company"))
    if legacy_desired_company not in ["", "Any", "NA"] and legacy_desired_company not in desired_companies:
        desired_companies.insert(0, legacy_desired_company)
    desired_company = desired_companies[0] if desired_companies else "Any"
    desired_categories = user_values(filters, "category", "desired_category")
    desired_genders = user_values(filters, "gender", "desired_gender")
    desired_classes = user_values(filters, "class", "desired_socioeconomic_class")
    desired_ages = user_values(filters, "age_range", "desired_age_range")
    desired_cities = user_values(filters, "city", "desired_city")
    desired_areas = user_values(filters, "area", "desired_area")
    desired_category = join_filter_values(desired_categories)
    desired_gender = join_filter_values(desired_genders)
    desired_class = join_filter_values(desired_classes)
    desired_age = join_filter_values(desired_ages)
    desired_city = join_filter_values(desired_cities)
    desired_area = join_filter_values(desired_areas)
    must_keywords = filters.get("must_have_keywords") or []
    avoid_keywords = filters.get("avoid_keywords") or []
    strict_category_match = bool(filters.get("strict_category_match", False))
    strict_logical_match = bool(filters.get("strict_logical_match", False))
    audience_intent = clean_text(filters.get("audience_intent", ""))
    logical_intent = clean_text(filters.get("logical_intent", ""))

    rows = []
    for _, row in catalog.iterrows():
        score = 0
        reasons = []
        hard_fail = False
        strict_hard_fail = False
        match_type_parts = []
        list_text = " ".join([str(row.get(c, "")) for c in ["List Name", "Company", "Category", "Original Category", "City / Coverage", "Area", "About"]])
        # Keyword evidence should come from the original list metadata, not from
        # the reduced cluster label. Otherwise every row in "Education & Students"
        # contains the word "Students" and generic school/education rows can
        # pass a stricter "university students" request.
        keyword_text = " ".join([str(row.get(c, "")) for c in ["List Name", "Company", "Original Category", "City / Coverage", "Area"]])

        company_priority_requested = bool(desired_companies)
        company_priority_match = False
        company_lexical_score = 0
        matched_company = ""
        if company_priority_requested:
            scores = []
            for wanted_company in desired_companies:
                wanted_score = max(
                    lexical_company_score(wanted_company, row.get("Company", ""), row.get("List Name", "")),
                    lexical_company_score(wanted_company, row.get("List Name", ""), row.get("Company", "")),
                )
                scores.append((wanted_score, wanted_company))
            company_lexical_score, matched_company = max(scores, key=lambda x: x[0]) if scores else (0, "")
            if company_lexical_score >= 58:
                company_priority_match = True
                score += 110 + company_lexical_score
                reasons.append(f"Company name mentioned in request; matched {matched_company} with lexical score {company_lexical_score}/100")
                match_type_parts.append("Company priority")
            else:
                score -= 20
                reasons.append("Different company from the names mentioned in request")

        logical_keyword_evidence = bool(strict_logical_match and must_keywords and text_contains_any(keyword_text, must_keywords))
        ok, add, cat_reasons, cat_match_types, cat_hard_fail = category_match(row["Category"], desired_categories, strict_category_match, company_priority_match)
        if cat_hard_fail and logical_keyword_evidence:
            # Product/industry search is logical: a row can pass if the raw list
            # metadata explicitly contains the requested product/industry
            # evidence, even if the reduced category cluster is imperfect.
            cat_hard_fail = False
            add = max(add, 18)
            cat_reasons = [f"Logical industry evidence matched: {logical_intent or desired_category}"]
            cat_match_types = ["Logical industry match"]
        score += add
        reasons.extend(cat_reasons)
        match_type_parts.extend(cat_match_types)
        if cat_hard_fail:
            hard_fail = True
            if strict_category_match:
                strict_hard_fail = True

        ok, add, reason, selected_gender = best_match_from_many(gender_match, row["Gender"], desired_genders)
        score += add
        reasons.append(reason)
        if not ok:
            if company_priority_match:
                score -= 10
                reasons.append("Gender mismatch, but kept because company name matches lexically")
                match_type_parts.append("Company-first relaxed gender")
            else:
                hard_fail = True
        elif add > 0:
            match_type_parts.append(reason)

        ok, add, reason, selected_class = best_match_from_many(class_match, row["Class"], desired_classes, allow_class_downgrade, use_allclasses_only_as_backup)
        score += add
        reasons.append(reason)
        if not ok:
            if company_priority_match:
                score -= 12
                reasons.append("Class mismatch, but kept because company name matches lexically")
                match_type_parts.append("Company-first relaxed class")
            else:
                hard_fail = True
        elif add > 0 or "backup" in reason.lower():
            match_type_parts.append(reason)

        ok, add, reason, selected_age = best_match_from_many(age_match, row["Age Range"], desired_ages, allow_age_extension)
        score += add
        reasons.append(reason)
        if not ok:
            if company_priority_match:
                score -= 12
                reasons.append("Age mismatch, but kept because company name matches lexically")
                match_type_parts.append("Company-first relaxed age")
            else:
                hard_fail = True
        elif add > 0 or "backup" in reason.lower():
            match_type_parts.append(reason)

        ok, add, reason, selected_city = simple_multi_value_match(row["City / Coverage"], desired_cities, "City/coverage", 16, 5, allow_na_backup=True)
        if desired_cities:
            if ok:
                score += add
                reasons.append(reason)
                match_type_parts.append(reason if add > 0 else "Broad city backup")
            elif company_priority_match:
                score -= 10
                reasons.append("City mismatch, but kept because company name matches lexically")
                match_type_parts.append("Company-first relaxed city")
            else:
                hard_fail = True
                reasons.append("City mismatch")

        ok, add, reason, selected_area = simple_multi_value_match(row["Area"], desired_areas, "Area", 14, 7, allow_na_backup=True)
        if desired_areas:
            if ok:
                score += add
                reasons.append(reason)
                match_type_parts.append(reason if add > 0 else "Area backup")
            else:
                score -= 10
                reasons.append("Area is different")

        if must_keywords and not text_contains_any(keyword_text, must_keywords):
            if strict_category_match:
                hard_fail = True
                strict_hard_fail = True
                if strict_logical_match:
                    reasons.append("Strict logical industry keyword missing")
                else:
                    reasons.append("Strict audience keyword missing")
            else:
                score -= 20
                reasons.append("Missing requested keyword")
        if avoid_keywords and text_contains_any(list_text, avoid_keywords):
            hard_fail = True
            reasons.append("Avoid keyword found")

        # Recency and list-quality bonuses.
        year = row.get("Created Year", np.nan)
        if pd.notna(year):
            if int(year) >= 2024:
                score += 8
                reasons.append("Very recent list")
            elif int(year) >= 2020:
                score += 4
                reasons.append("Recent enough list")
        if row["Unique / Special List"]:
            score += 3
            reasons.append("Special/unique list")
        if row.get("Exclusive Data", False):
            score += 10
            reasons.append("Exclusive JorMall list")
            match_type_parts.append("Exclusive data")
        if row.get("Most Unique Profile Version", False):
            score += 6
            reasons.append("Most unique/latest profile version")
        elif int(row.get("Profile Duplicate Group Size", 1) or 1) > 1:
            score -= 8
            reasons.append("Similar profile exists, lower uniqueness priority")
        if row["Duplicate Except Date"] and row["Preferred Duplicate Version"]:
            score += 2
            reasons.append("Newest exact duplicate version kept")

        if strict_hard_fail:
            # Strong audience requests such as "all university students" must not
            # be broadened into General, Restaurants, or other high-count lists,
            # even when Enhance Count or Max mode is enabled.
            continue
        if hard_fail and not enhance_count:
            continue
        if hard_fail and enhance_count:
            score -= 25
            match_type_parts.append("Enhanced count backup")

        candidate = row.to_dict()
        candidate.update({
            "Recommendation Score": int(score),
            "Match Type": " + ".join(match_type_parts) if match_type_parts else "General match",
            "Why Recommended": "; ".join(dict.fromkeys([r for r in reasons if r])),
            "Company Priority Requested": bool(company_priority_requested),
            "Company Priority Match": bool(company_priority_match),
            "Matched Requested Company": matched_company,
            "Company Lexical Score": int(company_lexical_score),
        })
        rows.append(candidate)

    rec = pd.DataFrame(rows)
    if rec.empty:
        return {
            "recommended": [],
            "summary": {
                "selected_lists": 0,
                "total_quantity": 0,
                "target_quantity": target_quantity,
                "target_met": False,
                "message": "No matching lists found. Try enabling Enhance Count or relaxing filters.",
            },
            "enhancements_applied": [],
        }

    rec = rec.sort_values(
        ["Company Priority Match", "Company Lexical Score", "Recommendation Score", "Exclusive Data", "Most Unique Profile Version", "Profile Duplicate Group Size", "Created Date", "Quantity"],
        ascending=[False, False, False, False, False, True, False, False],
    )

    before_unique = len(rec)
    # Recommendation uniqueness: show only the strongest list for the same audience profile.
    # This prevents recommending many historical versions of the same list with different dates.
    rec = rec.drop_duplicates("Profile Key Except Date", keep="first").copy()
    duplicate_profiles_suppressed = before_unique - len(rec)

    # If the request mentions a company and matching company data exists, keep
    # the optimizer focused on those company lists. This prevents the target
    # counter from choosing a less relevant non-company list just because it
    # numerically matches the requested quantity.
    company_priority_applied = False
    if desired_company not in ["Any", "NA", ""] and "Company Priority Match" in rec.columns and rec["Company Priority Match"].any():
        rec = rec[rec["Company Priority Match"]].copy()
        company_priority_applied = True

    exact_pool = rec[~rec["Match Type"].str.contains("Enhanced count backup", case=False, na=False)].copy()
    backup_pool = rec[rec["Match Type"].str.contains("Enhanced count backup", case=False, na=False)].copy()
    enhancements = []
    if strict_category_match and desired_category not in ["Any", "NA", ""]:
        enhancements.append(f"Strict {logical_intent or audience_intent or desired_category} intent applied; unrelated categories were excluded even in Max/Enhance mode")
    if company_priority_applied:
        enhancements.append("Company name(s) were mentioned; recommendations were prioritized from matching company data first")

    if target_quantity:
        # Target count is now an optimization goal. First try the strongest exact
        # pool; if Enhance Count is enabled, compare against a broader pool too.
        candidate_pools = []
        if not exact_pool.empty:
            candidate_pools.append(("exact", exact_pool))
        if enhance_count and not backup_pool.empty:
            candidate_pools.append(("enhanced", rec))
        if not candidate_pools:
            candidate_pools.append(("all", rec))

        selections = [(name, _target_aware_select(pool, max_lists, int(target_quantity))) for name, pool in candidate_pools]
        pool_name, selected = min(selections, key=lambda item: _selection_sort_key(item[1], int(target_quantity)))
        if pool_name == "enhanced":
            enhancements.append("Enhanced count used controlled backup lists to get closer to the target quantity")
        gap = _target_gap(selected, int(target_quantity))
        if int(selected["Quantity"].sum()) >= int(target_quantity):
            enhancements.append(f"Target optimizer reached the requested count; difference from target: {gap:,}")
        else:
            enhancements.append(f"Target optimizer selected all suitable available rows but is still short by {gap:,}")
    else:
        selected = rec.head(max_lists).copy()

    selected_total = int(selected["Quantity"].sum())
    available_total_after_filters = int(pd.to_numeric(rec["Quantity"], errors="coerce").fillna(0).sum()) if not rec.empty else 0
    target_quantity_int = int(target_quantity or 0)
    target_reached = bool(target_quantity_int and selected_total >= target_quantity_int) if target_quantity_int else None
    if target_quantity_int and target_reached:
        target_message = "Target reached. Review the selected lists before sending."
    elif target_quantity_int:
        shortage = max(0, target_quantity_int - selected_total)
        target_message = f"Target not reachable with the current logical filters. Maximum selected count is short by {shortage:,}."
    else:
        target_message = "Choose the following lists when sending"

    selected["Audience"] = selected["Gender"].astype(str) + " · " + selected["Category"].astype(str)
    selected["Location"] = selected["City / Coverage"].astype(str) + selected["Area"].apply(lambda x: "" if clean_text(x) in ["", "NA"] else " · " + clean_text(x))
    selected["Uniqueness"] = selected.apply(
        lambda r: "Exclusive / Most unique" if bool(r.get("Exclusive Data", False)) and bool(r.get("Most Unique Profile Version", False)) else ("Exclusive" if bool(r.get("Exclusive Data", False)) else ("Most unique" if bool(r.get("Most Unique Profile Version", False)) else "Unique enough")),
        axis=1,
    )
    output_cols = [
        "List ID", "List Name", "Company", "About", "Audience", "Class", "Age Range",
        "Location", "Quantity", "Created Date", "Uniqueness", "Exclusive Data", "Match Type",
        "Recommendation Score", "Company Priority Match", "Matched Requested Company", "Company Lexical Score", "Why Recommended",
    ]
    selected = selected[output_cols].copy()

    return {
        "recommended": selected.to_dict(orient="records"),
        "summary": {
            "selected_lists": int(len(selected)),
            "total_quantity": selected_total,
            "target_quantity": target_quantity_int,
            "target_difference": int(abs(selected_total - target_quantity_int)) if target_quantity_int else 0,
            "target_shortage": int(max(0, target_quantity_int - selected_total)) if target_quantity_int else 0,
            "target_overshoot": int(max(0, selected_total - target_quantity_int)) if target_quantity_int else 0,
            "target_met": target_reached,
            "target_match_mode": "Reach target first, then minimize overshoot" if target_quantity_int else "No target optimization",
            "target_available_quantity_after_filters": available_total_after_filters,
            "target_possible_after_filters": bool(available_total_after_filters >= target_quantity_int) if target_quantity_int else None,
            "available_recommendable_lists": int(len(catalog)),
            "duplicate_profiles_suppressed": int(duplicate_profiles_suppressed),
            "message": target_message,
        },
        "enhancements_applied": enhancements,
    }



def build_selection_chart_data(recommended: pd.DataFrame, top_n: int = 12) -> List[Dict[str, Any]]:
    """Return compact bar-chart rows for the selected/recommended lists."""
    if recommended is None or recommended.empty or "Quantity" not in recommended:
        return []
    chart = recommended.copy()
    chart["Quantity"] = pd.to_numeric(chart["Quantity"], errors="coerce").fillna(0).astype(int)
    if "List Name" not in chart:
        return []
    chart = chart.sort_values("Quantity", ascending=False).head(top_n)
    return [
        {
            "label": str(row.get("List Name", ""))[:64],
            "quantity": int(row.get("Quantity", 0)),
            "profile": str(row.get("Audience", row.get("Category", ""))),
        }
        for _, row in chart.iterrows()
    ]

def catalog_summary(df: pd.DataFrame) -> Dict[str, Any]:
    ready = df[df["Ready for Recommendation"]]
    raw_categories = ready["Original Category"].nunique() if "Original Category" in ready else ready["Category"].nunique()
    category_groups = ready["Business Category Group"].nunique() if "Business Category Group" in ready else ready["Category"].nunique()
    reduction = 0.0
    if raw_categories:
        reduction = (1 - (category_groups / raw_categories)) * 100
    return {
        "total_rows": int(len(df)),
        "ready_lists": int(len(ready)),
        "dropped_old_or_invalid": int(len(df) - len(ready)),
        "source_excluded_lists": int((~df["Source Eligible"]).sum()) if "Source Eligible" in df else 0,
        "source_excluded_quantity": int(df.loc[~df["Source Eligible"], "Quantity"].sum()) if "Source Eligible" in df and "Quantity" in df else 0,
        "total_quantity_ready": int(ready["Quantity"].sum()) if not ready.empty else 0,
        "duplicate_except_date_rows": int(df["Duplicate Except Date"].sum()) if "Duplicate Except Date" in df else 0,
        "special_lists_kept": int(df["Unique / Special List"].sum()) if "Unique / Special List" in df else 0,
        "raw_categories": int(raw_categories),
        "category_groups": int(category_groups),
        "category_reduction_percent": round(float(reduction), 1),
        "latest_date": str(ready["Created Date"].replace("NA", np.nan).dropna().max()) if not ready.empty else "NA",
    }


def top_chart_data(df: pd.DataFrame, column: str, top_n: int = 10) -> List[Dict[str, Any]]:
    ready = df[df["Ready for Recommendation"]]
    if ready.empty or column not in ready:
        return []
    data = (
        ready.groupby(column, dropna=False)["Quantity"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )
    return [{"label": str(r[column]), "value": int(r["Quantity"])} for _, r in data.iterrows()]
