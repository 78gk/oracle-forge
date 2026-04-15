"""Assert every Yelp query.json question has a Postgres template (optional dry-run)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.dab_yelp_postgres import POSTGRES_SQL_BY_QUESTION, postgres_sql_for_yelp_question


def main() -> None:
    dab = ROOT / "DataAgentBench" / "query_yelp"
    missing = []
    for qdir in sorted(dab.glob("query*")):
        if not qdir.is_dir() or not re.fullmatch(r"query\d+", qdir.name):
            continue
        qpath = qdir / "query.json"
        if not qpath.exists():
            continue
        raw = json.loads(qpath.read_text(encoding="utf-8"))
        question = raw if isinstance(raw, str) else str(raw.get("query", ""))
        if not question.strip():
            continue
        if postgres_sql_for_yelp_question(question) is None:
            missing.append((qdir.name, question[:80]))
    if missing:
        print("Missing POSTGRES_SQL_BY_QUESTION for:")
        for qid, q in missing:
            print(f"  {qid}: {q!r}")
        sys.exit(1)
    print(f"OK: {len(POSTGRES_SQL_BY_QUESTION)} templates cover all query_yelp query.json files.")


if __name__ == "__main__":
    main()
