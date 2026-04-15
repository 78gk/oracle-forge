from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.dab_evaluator import run_probes


def main() -> None:
    output_path = ROOT / "eval" / "probe_results.json"
    probes_path = ROOT / "eval" / "adversarial_probes.json"
    report = run_probes(probes_path)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"probe_validity": report["probe_validity"], "probe_count": report["probe_count"]}, indent=2))


if __name__ == "__main__":
    main()
