"""
Fork-style evaluation entry (rafia-10 / DataAgentBench README).

Examples::

    python -m eval.harness --datasets yelp --query_ids 1 --n_trials 1
    python -m eval.harness --datasets yelp agnews --n_trials 1 --max-queries 2

Maps to :func:`eval.run_dab_eval.run_benchmark` / ``run_dab_eval`` CLI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _translate_argv(argv: list[str]) -> list[str]:
    """Turn fork-style flags into ``run_dab_eval`` arguments."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--n_trials", "--n-trials"):
            if i + 1 >= len(argv):
                raise SystemExit(f"{a} requires a value")
            out.extend(["--trials", argv[i + 1]])
            i += 2
            continue
        if a == "--datasets":
            ds: list[str] = []
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                ds.append(argv[i])
                i += 1
            if not ds:
                raise SystemExit("--datasets requires at least one dataset key")
            if len(ds) == 1:
                out.extend(["--scope", "single", "--dataset", ds[0]])
            else:
                out.extend(["--scope", "multi", "--datasets", ",".join(ds)])
            continue
        if a in ("--query_ids", "--query-ids"):
            ids: list[str] = []
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                ids.append(argv[i].strip(","))
                i += 1
            if not ids:
                raise SystemExit("--query_ids requires at least one id")
            out.extend(["--query-ids", ",".join(ids)])
            continue
        if a == "--no_hints":
            # Fork flag; we do not use hint toggles in this harness — ignore.
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def main() -> None:
    from eval.run_dab_eval import build_parser, run_benchmark

    mapped = _translate_argv(sys.argv[1:])
    sys.argv = [sys.argv[0]] + mapped
    args = build_parser().parse_args()
    run_benchmark(args)


if __name__ == "__main__":
    main()
