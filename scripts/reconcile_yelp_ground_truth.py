"""
Recompute DataAgentBench Yelp ground_truth.csv lines from the local BSON + DuckDB slice.

Run (dry):  python reconcile_yelp_ground_truth.py
Apply:      python reconcile_yelp_ground_truth.py --write

Use when category/rating definitions are derived from descriptions (no Mongo categories in BSON).
"""
from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import duckdb
from bson import decode_all

from yelp_dab_categories import canonical_category_label, categories_for_business, categories_from_featuring_block
from yelp_dab_derived import accepts_credit_cards, has_wifi, state_from_description

REPO = Path(__file__).resolve().parents[1]


def q1(docs, reviews) -> str:
    by_id = {str(d["business_id"]): d for d in docs}
    stars: list[int] = []
    for _rid, _uid, bref, rating, _date in reviews:
        d = by_id.get(to_mid(bref))
        if not d:
            continue
        desc = d.get("description") or ""
        if "Indianapolis" in desc and ", IN" in desc:
            stars.append(int(rating))
    if not stars:
        return "0"
    return str(statistics.mean(stars))


def q3(docs, reviews) -> str:
    import re

    by_id = {str(d["business_id"]): d for d in docs}

    def parking_ok(b: dict) -> bool:
        a = str(b.get("attributes") or "")
        if "'BikeParking': 'True'" in a:
            return True
        return bool(re.search(r"BusinessParking.*(garage|street|validated|lot|valet).*: True", a))

    seen: set[str] = set()
    for _rid, _uid, bref, _rating, date_s in reviews:
        if "2018" not in str(date_s):
            continue
        mid = to_mid(bref)
        d = by_id.get(mid)
        if not d or not parking_ok(d):
            continue
        seen.add(mid)
    return str(len(seen))


def load_docs():
    p = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_business/yelp_db/business.bson"
    return decode_all(p.read_bytes())


def load_reviews():
    duck = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_user.db"
    con = duckdb.connect(str(duck))
    return con.execute(
        "SELECT review_id, user_id, business_ref, rating, date FROM review"
    ).fetchall()


def load_users():
    duck = REPO / "DataAgentBench/query_yelp/query_dataset/yelp_user.db"
    con = duckdb.connect(str(duck))
    return con.execute('SELECT user_id, yelping_since FROM "user"').fetchall()


def to_mid(ref: str) -> str:
    if ref.startswith("businessref_"):
        return ref.replace("businessref_", "businessid_", 1)
    return ref


def q2(docs, reviews) -> str:
    by_id = {str(d["business_id"]): d for d in docs}
    st_rev: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, _date in reviews:
        d = by_id.get(to_mid(bref))
        if not d:
            continue
        st = state_from_description(d.get("description") or "")
        if st:
            st_rev[st].append(int(rating))
    top = max(st_rev.items(), key=lambda kv: len(kv[1]))
    avg = statistics.mean(top[1])
    return f"{top[0]},{avg}"


def q4(docs, reviews) -> str:
    by_id = {str(d["business_id"]): d for d in docs}
    cat_biz: dict[str, set[str]] = defaultdict(set)
    cat_stars: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, _date in reviews:
        mid = to_mid(bref)
        d = by_id.get(mid)
        if not d or not accepts_credit_cards(d.get("attributes")):
            continue
        for raw in categories_for_business(d):
            key = canonical_category_label(raw)
            cat_biz[key].add(mid)
            cat_stars[key].append(int(rating))
    best = max(cat_biz.items(), key=lambda kv: len(kv[1]))
    cat = best[0]
    avg = statistics.mean(cat_stars[cat])
    return f"{cat},{avg}"


def q5(docs, reviews) -> str:
    by_id = {str(d["business_id"]): d for d in docs}
    st_biz: dict[str, set[str]] = defaultdict(set)
    for d in docs:
        if not has_wifi(d.get("attributes")):
            continue
        st = state_from_description(d.get("description") or "")
        if not st:
            continue
        st_biz[st].add(str(d["business_id"]))
    top = max(st_biz.items(), key=lambda kv: len(kv[1]))
    st = top[0]
    stars: list[int] = []
    for _rid, _uid, bref, rating, _date in reviews:
        mid = to_mid(bref)
        if mid in st_biz[st]:
            stars.append(int(rating))
    avg = statistics.mean(stars)
    return f"{st},{avg}"


def q6(docs, reviews) -> str:
    by_id = {str(d["business_id"]): d for d in docs}

    def in_range(ds: str) -> bool:
        try:
            dt = datetime.strptime(ds[:10], "%Y-%m-%d")
            return datetime(2016, 1, 1) <= dt <= datetime(2016, 6, 30)
        except Exception:
            return False

    biz_stars: dict[str, list[int]] = defaultdict(list)
    for _rid, _uid, bref, rating, date_s in reviews:
        if not in_range(date_s):
            continue
        biz_stars[to_mid(bref)].append(int(rating))
    qualified = {b: v for b, v in biz_stars.items() if len(v) >= 5}
    best = max(qualified.items(), key=lambda kv: statistics.mean(kv[1]))
    bdoc = by_id[best[0]]
    name = str(bdoc.get("name") or "")
    cats = categories_from_featuring_block(bdoc.get("description") or "")
    if not cats:
        cats = categories_for_business(bdoc)[:6]
    parts = [name] + cats
    return ",".join(parts)


def q7(docs, reviews, users) -> str:
    by_id = {str(d["business_id"]): d for d in docs}
    u2016 = {str(uid) for uid, ys in users if ys and str(ys).startswith("2016")}
    cat_n: dict[str, int] = defaultdict(int)
    for _rid, uid, bref, _rating, date_s in reviews:
        if str(uid) not in u2016:
            continue
        if not date_s or not str(date_s)[:4].isdigit() or int(str(date_s)[:4]) < 2016:
            continue
        d = by_id.get(to_mid(bref))
        if not d:
            continue
        for raw in categories_for_business(d):
            cat_n[raw] += 1
    top5 = [c for c, _n in sorted(cat_n.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    return "\n".join(top5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Overwrite ground_truth.csv files")
    args = parser.parse_args()
    docs = load_docs()
    reviews = load_reviews()
    users = load_users()
    rows = {
        "query1": q1(docs, reviews),
        "query2": q2(docs, reviews),
        "query3": q3(docs, reviews),
        "query4": q4(docs, reviews),
        "query5": q5(docs, reviews),
        "query6": q6(docs, reviews),
        "query7": q7(docs, reviews, users),
    }
    base = REPO / "DataAgentBench/query_yelp"
    for qid, text in rows.items():
        path = base / qid / "ground_truth.csv"
        print(f"{qid}: {text[:120]}{'...' if len(text) > 120 else ''}")
        if args.write:
            path.write_text(text if qid != "query7" else text + "\n", encoding="utf-8")
            print(f"  wrote {path}")


if __name__ == "__main__":
    main()
