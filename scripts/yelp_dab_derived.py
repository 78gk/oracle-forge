"""
Derive DAB-aligned fields from Yelp BSON/Mongo business docs (same logic as Postgres seed).

Used by seed_yelp_postgres.py so SQL templates stay simple and match ground_truth.csv.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Set


def state_from_description(desc: str) -> str | None:
    """Two-letter US state: last `, ST` before comma/period/space (validated vs Q2 GT)."""
    if not desc:
        return None
    st: str | None = None
    for m in re.finditer(r", ([A-Z]{2})(?=,|\.|\s)", desc):
        st = m.group(1)
    return st


def _attrs_dict(attrs: Any) -> dict[str, Any]:
    if isinstance(attrs, dict):
        return attrs
    return {}


def accepts_credit_cards(attrs: Any) -> bool:
    d = _attrs_dict(attrs)
    return d.get("BusinessAcceptsCreditCards") == "True"


def has_wifi(attrs: Any) -> bool:
    """WiFi offered: free or paid (exclude u'no' / 'no')."""
    d = _attrs_dict(attrs)
    raw = d.get("WiFi")
    if raw is None:
        return False
    s = str(raw).lower()
    if "free" in s or "paid" in s:
        return True
    return False


def extract_category_tokens(description: str) -> Set[str]:
    """Yelp-style category labels from synthetic benchmark descriptions."""
    if not description:
        return set()
    cats: set[str] = set()
    patterns = [
        r"specializing in ([^.]+)\.",
        r"specializes in ([^.]+)\.",
        r"categories of ([^.]+)\.",
        r"category of ([^.]+)\.",
        r"in the category of ([^.]+)\.",
        r"categories such as ([^.]+)\.",
        r"fusion of flavors across categories such as ([^.]+)\.",
        r"featuring ([^.]+)\.",
        r"including ([^.]+)\.",
        r"offers ([^.]+)\.",
        r"offerings, including ([^.]+)\.",
        r"showcases ([^.]+)\.",
        r"options ranging from ([^.]+)\.",
        r"selection of ([^.]+)\.",
        r"menu featuring ([^.]+)\.",
        r"menu that showcases ([^.]+)\.",
        r"perfect for ([^.]+)\.",
        r"destination for ([^.]+)\.",
        r"seeking ([^.]+)\.",
        r"enjoying ([^.]+)\.",
        r"atmosphere for ([^.]+)\.",
        r"experience with options for ([^.]+)\.",
        r"array of dishes in the category of ([^.]+)\.",
        r"menu in the category of ([^.]+)\.",
        r"delightful array of options, ([^.]+)\.",
        r"delightful mix of ([^.]+)\.",
        r"delightful selection of ([^.]+)\.",
        r"great atmosphere for enjoying ([^.]+)\.",
        r"diverse menu featuring ([^.]+)\.",
        r"diverse menu that showcases ([^.]+)\.",
        r"diverse experience with options for ([^.]+)\.",
        r"delightful dining experience featuring ([^.]+)\.",
    ]
    for pat in patterns:
        for m in re.finditer(pat, description, re.I):
            chunk = m.group(1).strip().strip("'\"")
            for part in chunk.split(","):
                p = part.strip()
                if len(p) < 2:
                    continue
                if p.lower().startswith("and "):
                    p = p[4:].strip()
                if p.lower().startswith("to "):
                    continue
                p = re.sub(r"\s+making\s+.*$", "", p, flags=re.I)
                p = re.sub(r"\s+for all your.*$", "", p, flags=re.I)
                p = re.sub(r"\s+for those seeking.*$", "", p, flags=re.I)
                if p:
                    cats.add(p)
    return cats


def category_rows_for_business(business_id: str, description: str) -> list[tuple[str, str]]:
    """Rows for business_category table: (business_id, category)."""
    bid = str(business_id)
    return [(bid, c) for c in sorted(extract_category_tokens(description))]
