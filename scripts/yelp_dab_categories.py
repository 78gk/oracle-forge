"""
Canonical Yelp category tokens for the DAB local slice (BSON + DuckDB).

BSON does not include Mongo `categories`; we parse description text and normalize
labels so multiset eval matches `ground_truth.csv` (e.g. Restaurant vs Restaurants).
"""
from __future__ import annotations

import re
from typing import Any, List, Set

from yelp_dab_derived import extract_category_tokens


def canonical_category_label(label: str) -> str:
    t = label.strip()
    if t == "Restaurants":
        return "Restaurant"
    return t


def categories_for_business(doc: dict[str, Any]) -> List[str]:
    """Category labels for counting/review stats (preserve Yelp plurals like Restaurants)."""
    raw = doc.get("categories")
    if isinstance(raw, list) and raw:
        out = [str(x).strip() for x in raw if str(x).strip()]
        seen: Set[str] = set()
        uniq: List[str] = []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq
    tokens = set(extract_category_tokens(doc.get("description") or ""))
    junk = re.compile(r"^(perfect|a |an )", re.I)
    cleaned: Set[str] = set()
    for t in tokens:
        if junk.search(t) or len(t) > 120:
            continue
        cleaned.add(t)
    return sorted(cleaned)


def categories_from_featuring_block(description: str) -> List[str]:
    """
    Primary category list for benchmark Q6-style answers: text between
    'featuring ' / 'including ' and the sentence-ending period.
    """
    if not description:
        return []
    m = re.search(r"(?:featuring|including) ([^.]+)\.", description, re.I)
    if not m:
        return []
    chunk = m.group(1).strip()
    parts = [p.strip() for p in chunk.split(",")]
    out: List[str] = []
    for p in parts:
        pl = p.lower()
        if pl.startswith("perfect ") or pl.startswith("making ") or pl.startswith("to "):
            break
        if len(p) < 2:
            continue
        out.append(p.strip())
    return out
