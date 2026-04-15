#!/usr/bin/env python3
"""
Convenience runner for the KB injection test suite.
Run this from the project root — no path wrangling needed.

Usage:
    python run_injection_tests.py                  # full suite + save results
    python run_injection_tests.py --verbose        # full suite with LLM answers
    python run_injection_tests.py --update-log     # full suite + update INJECTION_TEST_LOG.md
    python run_injection_tests.py --validate-paths # path check only (no API call)
    python run_injection_tests.py --test-single architecture/memory.md
    python run_injection_tests.py --results-dir ./injection_results

All output (JSON + Markdown) goes to injection_results/ by default.
Reads GROQ_API_KEY from .env at the project root.
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent

# ── Read GROQ_API_KEY directly from .env (bypasses environment masking) ────
def _read_env_file(path: Path) -> dict:
    """Parse key=value lines from a .env file, stripping quotes."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result

env_vars = _read_env_file(ROOT / ".env")
groq_api_key = env_vars.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")

if not groq_api_key:
    print("ERROR: GROQ_API_KEY not found in .env or environment.")
    sys.exit(1)

# ── Ensure kb/ is importable ───────────────────────────────────────────────
sys.path.insert(0, str(ROOT / "kb"))

# ── Build argv: inject defaults then append user args ─────────────────────
user_args = sys.argv[1:]

defaults = {
    "--kb-path":      str(ROOT / "kb"),
    "--results-dir":  str(ROOT / "injection_results"),
    "--api-key":      groq_api_key,       # always pass key explicitly
}

# Always append --update-log unless user explicitly passed it already
always_flags = ["--update-log"]

# Build the final argument list
final_args = [sys.argv[0]]

for flag, value in defaults.items():
    if not any(a == flag or a.startswith(flag + "=") for a in user_args):
        final_args += [flag, value]

for flag in always_flags:
    if flag not in user_args:
        final_args.append(flag)

final_args += user_args
sys.argv = final_args

# ── Hand off to injection_test.main() ─────────────────────────────────────
import injection_test  # noqa: E402
injection_test.main()
