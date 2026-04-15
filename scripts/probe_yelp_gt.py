"""Offline probe: recompute DAB Yelp metrics vs ground_truth.csv using yelp_dab_derived."""
from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

import duckdb
from bson import decode_all

from yelp_dab_derived import (
    accepts_credit_cards,
    extract_category_tokens,
    has_wifi,
    state_from_description,
)

REPO = Path(__file__).resolve().parents[1]


def load():
    bson_path = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_business/yelp_db/business.bson"
    docs = decode_all(bson_path.read_bytes())
    con = duckdb.connect(str(REPO / "DataAgentBench/query_yelp/query_dataset/yelp_user.db"))
    reviews = con.execute(
        "SELECT review_id, user_id, business_ref, rating, date, text FROM review"
    ).fetchall()
    users = con.execute('SELECT user_id, yelping_since FROM "user"').fetchall()
    return docs, reviews, users


def to_mid(ref: str) -> str:
    if ref.startswith("businessref_"):
        return ref.replace("businessref_", "businessid_", 1)
    return ref


def main() -> None:
    docs, reviews, users = load()
    by_id = {str(d["business_id"]): d for d in docs}

    # --- Q2 ---
    st_rev: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, _d, _t in reviews:
        d = by_id.get(to_mid(bref))
        if not d:
            continue
        st = state_from_description(d.get("description") or "")
        if st:
            st_rev[st].append(int(rating))
    top = max(st_rev.items(), key=lambda kv: len(kv[1]))
    print("Q2", top[0], statistics.mean(top[1]), "expected ~3.699 PA")

    # --- Q4 ---
    cat_biz: dict[str, set[str]] = defaultdict(set)
    cat_stars: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, _d, _t in reviews:
        mid = to_mid(bref)
        d = by_id.get(mid)
        if not d or not accepts_credit_cards(d.get("attributes")):
            continue
        for cat in extract_category_tokens(d.get("description") or ""):
            cat_biz[cat].add(mid)
            cat_stars[cat].append(int(rating))
    best = max(cat_biz.items(), key=lambda kv: len(kv[1]))
    print(
        "Q4",
        best[0],
        len(best[1]),
        statistics.mean(cat_stars[best[0]]),
        "expected Restaurant ~3.633676",
    )

    # --- Q5: count businesses (not reviews) per state with WiFi ---
    st_biz: dict[str, set[str]] = defaultdict(set)
    st_stars: dict[str, list[int]] = defaultdict(list)
    for d in docs:
        attrs = d.get("attributes")
        if not has_wifi(attrs):
            continue
        st = state_from_description(d.get("description") or "")
        if not st:
            continue
        st_biz[st].add(str(d["business_id"]))
    top5 = max(st_biz.items(), key=lambda kv: len(kv[1]))
    st5 = top5[0]
    for _rid, _uid, bref, rating, _d, _t in reviews:
        mid = to_mid(bref)
        if mid not in st_biz[st5]:
            continue
        st_stars[st5].append(int(rating))
    print("Q5", st5, len(st_biz[st5]), statistics.mean(st_stars[st5]), "expected PA 3.48")

    # --- Q6 ---
    from datetime import datetime

    def in_range(ds: str) -> bool:
        try:
            dt = datetime.strptime(ds[:10], "%Y-%m-%d")
            return datetime(2016, 1, 1) <= dt <= datetime(2016, 6, 30)
        except Exception:
            return False

    biz_stars: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, date_s, _t in reviews:
        if not in_range(date_s):
            continue
        mid = to_mid(bref)
        biz_stars[mid].append(int(rating))
    qualified = {b: v for b, v in biz_stars.items() if len(v) >= 5}
    best_b = max(qualified.items(), key=lambda kv: statistics.mean(kv[1]))
    bdoc = by_id[best_b[0]]
    print(
        "Q6",
        bdoc.get("name"),
        statistics.mean(best_b[1]),
        sorted(extract_category_tokens(bdoc.get("description") or "")),
    )

    # --- Q7 ---
    u2016 = {str(uid) for uid, ys in users if ys and str(ys).startswith("2016")}
    cat_n: dict[str, int] = defaultdict(int)
    for _rid, uid, bref, _rating, date_s, _t in reviews:
        if str(uid) not in u2016:
            continue
        if not date_s or not str(date_s)[:4].isdigit() or int(str(date_s)[:4]) < 2016:
            continue
        d = by_id.get(to_mid(bref))
        if not d:
            continue
        for cat in extract_category_tokens(d.get("description") or ""):
            cat_n[cat] += 1
    top7 = sorted(cat_n.items(), key=lambda kv: -kv[1])[:10]
    print("Q7", top7)


def probe_restaurant_primary_only() -> None:
    """Only reviews where Restaurants is the first category token in a primary phrase."""
    import re

    docs, reviews, _users = load()
    by_id = {str(d["business_id"]): d for d in docs}
    from yelp_dab_derived import accepts_credit_cards

    def first_restaurantish(desc: str) -> bool:
        if not desc:
            return False
        for pat in (
            r"specializing in ([^.]+)\.",
            r"featuring ([^.]+)\.",
            r"including ([^.]+)\.",
        ):
            m = re.search(pat, desc, re.I)
            if m:
                first = m.group(1).split(",")[0].strip().strip("'\"")
                return first in ("Restaurants", "Restaurant")
        return False

    stars: list[int] = []
    for _rid, _uid, bref, rating, _d, _t in reviews:
        mid = to_mid(bref)
        d = by_id.get(mid)
        if not d or not accepts_credit_cards(d.get("attributes")):
            continue
        if first_restaurantish(d.get("description") or ""):
            stars.append(int(rating))
    if stars:
        print(
            "restaurant_primary_only",
            len(stars),
            statistics.mean(stars),
            "GT",
            3.633676092544987,
        )


def probe_primary_category() -> None:
    import re

    docs, reviews, _users = load()
    by_id = {str(d["business_id"]): d for d in docs}
    from yelp_dab_derived import accepts_credit_cards

    def primary_cat(desc: str) -> str | None:
        if not desc:
            return None
        for pat in (
            r"featuring ([^.]+)\.",
            r"including ([^.]+)\.",
            r"specializing in ([^.]+)\.",
            r"offers ([^.]+)\.",
        ):
            m = re.search(pat, desc, re.I)
            if m:
                return m.group(1).split(",")[0].strip().strip("'\"")
        return None

    cat_biz: dict[str, set[str]] = defaultdict(set)
    cat_stars: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, _d, _t in reviews:
        mid = to_mid(bref)
        d = by_id.get(mid)
        if not d or not accepts_credit_cards(d.get("attributes")):
            continue
        c = primary_cat(d.get("description") or "")
        if not c:
            continue
        if c == "Restaurants":
            c = "Restaurant"
        cat_biz[c].add(mid)
        cat_stars[c].append(int(rating))
    best = max(cat_biz.items(), key=lambda kv: len(kv[1]))
    print(
        "primary_cat",
        best[0],
        len(best[1]),
        statistics.mean(cat_stars[best[0]]),
    )


if __name__ == "__main__":
    main()
    probe_restaurant_primary_only()
    probe_primary_category()
