# Oracle Forge — Data Agent

A context-injection knowledge base for an LLM-powered multi-database analytics agent, built for the [DAB benchmark](https://github.com/DABenchmark).

## How It Works

Every file in `kb/` is a self-contained document designed to be injected directly into an LLM context window. No RAG, no embeddings — documents are loaded by path and pasted as system context before query execution.

Documents are validated with **injection tests**: a fresh LLM session receives only the document, is asked a question it should answer, and must match ≥70% of expected keywords to pass.

## Repository Structure

```markdown
oracle-forge-data-agent/
├── kb/                              # The agent's knowledge base
│   ├── architecture/                # How the agent thinks
│   │   ├── memory.md                  # Three-layer memory system
│   │   ├── conductor_worker_pattern.md # Multi-database routing
│   │   ├── openai_layers.md           # Six-layer context architecture
│   │   ├── autodream_consolidation.md # Weekly session compression
│   │   ├── tool_scoping_philosophy.md # 40+ tight tools > 5 generic
│   │   └── evaluation_harness_schema.md # Trace schema + pass@1
│   ├── domain/                      # DAB dataset knowledge
│   │   ├── databases/               # PostgreSQL, MongoDB, SQLite, DuckDB schemas
│   │   ├── joins/                   # Cross-DB join key transformations
│   │   ├── unstructured/            # Sentiment + text extraction patterns
│   │   └── domain_terms/            # Business glossary (telecom, Yelp, healthcare)
│   ├── correction/                  # Self-learning correction loop
│   │   ├── failure_log.md           # Chronological failures + fixes
│   │   ├── failure_by_category.md   # Failures by DAB's 4 categories
│   │   ├── resolved_patterns.md     # Permanent fixes with confidence scores
│   │   └── regression_prevention.md # Regression test rules
│   ├── evaluation/                  # DAB benchmark reference
│   │   ├── dab_scoring_method.md    # pass@1 definition and calculation
│   │   └── submission_format.md     # PR requirements + AGENT.md template
│   ├── injection_test.py            # Injection test runner (Groq Llama)
│   └── CHANGELOG.md                 # Version history
│
├── planning/                        # Team planning documents
├── requirements.txt                 # Python dependencies
└── setup_groq_tests.sh              # API key setup + test quickstart
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure Groq API key (interactive — writes key to .env)
bash setup_groq_tests.sh

# Or add to .env manually (run_injection_tests.py reads this automatically)
echo 'GROQ_API_KEY="your-key-here"' >> .env

# Or export for the current shell session only
export GROQ_API_KEY="your-key-here"
```

## Running Injection Tests

Use `run_injection_tests.py` from the **project root** — it reads `.env` automatically and saves timestamped results to `injection_results/`.

```bash
# Full suite — saves JSON + Markdown to injection_results/
python run_injection_tests.py

# Full suite with LLM answers printed
python run_injection_tests.py --verbose

# Full suite + update kb/INJECTION_TEST_LOG.md
python run_injection_tests.py --update-log

# Check that all document paths resolve (no API call)
python run_injection_tests.py --validate-paths

# Test a single document
python run_injection_tests.py --test-single architecture/memory.md

# Custom results directory
python run_injection_tests.py --results-dir ./my_results
```

**Direct runner** (if you need lower-level control or are calling from a script):

```bash
# Must be run from the project root; pass --kb-path and --api-key explicitly
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY"
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --verbose
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --test-single architecture/memory.md
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --validate-paths
```

Results are written to `injection_results/` as `injection_test_YYYY-MM-DD_HH-MM-SS.json` and `.md`.

Current pass rate: **21/21 (100%)** — see `injection_results/`.

## DataAgentBench Setup and Test Run

Use this section when you want to run DAB end-to-end from this project while we improve agent performance.

### 1) Prepare DataAgentBench (Fork-First)

Use your team fork as the primary source of truth for runtime/agent changes.

```bash
# from oracle-forge root
git lfs install
git clone https://github.com/gemechisworku/DataAgentBench.git
cd DataAgentBench
git remote add upstream https://github.com/ucbepic/DataAgentBench.git
git lfs pull
```

Recommended branch model:
- `main` in your fork tracks upstream-compatible baseline
- feature branches for experiments/fixes (e.g., `feature/openrouter-dab`)
- merge tested changes into your fork `main`

### 2) Create Python environment

`conda` is optional. We use `uv` + `venv` reliably on Windows.

```bash
# from DataAgentBench/
uv venv --python 3.11 .venv
# PowerShell
.\\.venv\\Scripts\\Activate.ps1

uv pip install openai python-dotenv pyyaml pandas numpy duckdb pymongo sqlalchemy psycopg2-binary autogen-core "autogen-ext[docker]==0.7.5" docker colorlog asyncio-atexit
```

### 3) Configure model/provider credentials

Create `DataAgentBench/.env`:

```env
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_SITE_URL=https://your-site.example
OPENROUTER_APP_NAME=OracleForge-DAB
```

### 4) Choose execution backend

Docker backend is benchmark-faithful. Local backend is useful for development when Docker is unavailable.

```bash
# benchmark-faithful
docker build -t python-data:3.12 .

# dev fallback (PowerShell)
$env:DAB_EXECUTOR="local"
```

### 4b) Start MCP Toolbox for Oracle Forge eval (Docker, required)

`eval/run_dab_eval.py` uses Oracle Forge's MCP tool client (not DAB's built-in DataAgent runtime), so MCP Toolbox must be up before evaluation.

1. Create root `.env` from `.env.example` and set DB/toolbox values:
   - `MCP_BASE_URL`
   - `POSTGRES_DSN`
   - `MONGODB_URI`
   - `MONGODB_DATABASE`
   - `SQLITE_PATH`
   - `DUCKDB_PATH`
   - keep `ORACLE_FORGE_MOCK_MODE=false`
   - keep `ORACLE_FORGE_ALLOW_MOCK_FALLBACK=false`
2. Start Docker Desktop, then bring up databases and seed Yelp Mongo data:

```powershell
docker compose -f mcp/docker-compose.yml up -d postgres mongo
docker compose -f mcp/docker-compose.yml --profile seed run --rm mongo-seed
```

3. Start/recreate Toolbox:

```powershell
docker compose -f mcp/docker-compose.yml up -d --force-recreate toolbox
```

4. Verify MCP is reachable:

```powershell
.\scripts\mcp_status.ps1
```

Note:
- Current Toolbox config exposes `postgres_sql_query`, `sqlite_sql_query`, and Mongo aggregate tools.
- For DAB datasets that declare a DuckDB file (for example Yelp `user_database`), the agent uses a local DuckDB SQL fallback via `DUCKDB_PATH`.
- Ensure the Python environment running eval has the `duckdb` package installed.

Or manual MCP check:

```powershell
$body = '{"jsonrpc":"2.0","id":"tools-list","method":"tools/list","params":{}}'
curl.exe -X POST http://localhost:5000/mcp -H "Content-Type: application/json" -d $body
```

5. Optional one-command startup wrapper:

```powershell
.\scripts\mcp_up.ps1
```

6. Shut down when done:

```powershell
.\scripts\mcp_down.ps1
```

If MCP is unreachable, eval now fails fast with an explicit error instead of silently using mock data.

### 5) Run a first DAB built-in agent query test

```bash
# from DataAgentBench/
python run_agent.py --dataset stockindex --query_id 1 --llm openrouter/openai/gpt-4o-mini --iterations 60 --root_name smoke_or_0
```

Logs are saved under:
`DataAgentBench/query_<dataset>/query<id>/logs/data_agent/<root_name>/`

### 6) Validate the run

```bash
python -c "from pathlib import Path; import json; from common_scaffold.validate.validate import validate; q=Path('query_stockindex/query1'); r=q/'logs'/'data_agent'/'smoke_or_0'/'final_agent.json'; d=json.loads(r.read_text(encoding='utf-8')); print(validate(q, d['final_result'], d['terminate_reason']))"
```

Expected for `stockindex/query1`: `is_valid: True` and target symbol `399001.SZ`.

### 7) Run Oracle Forge eval against DAB (after MCP is up)

Set these once in root `.env` (no inline PowerShell env args required):
- `MCP_BASE_URL=http://localhost:5000`
- `ORACLE_FORGE_MOCK_MODE=false`
- `ORACLE_FORGE_ALLOW_MOCK_FALLBACK=false`
- `LLM_PROVIDER=openrouter`
- `OPENROUTER_API_KEY=<your_key>`
- `MODEL_NAME=openai/gpt-4o-mini`
- `DAB_DATASET=yelp`
- `DAB_TRIALS_PER_QUERY=1` (smoke) or `50` (full)

Then run:

```powershell
python eval\run_dab_eval.py
```

Outputs are written to:
- `eval/results.json`
- `eval/score_log.jsonl`

## Team Workflow for Agent Improvement

Use this loop to improve pass rates without losing traceability:

1. Update knowledge artifacts in this repo (`kb/`, `probes/`, `utils/`) based on failures.
2. Port practical fixes into `DataAgentBench/common_scaffold/` (prompting, tool usage, routing/execution behavior).
3. Run targeted DAB query tests first (single query, fixed `root_name` per run).
4. Validate with `common_scaffold.validate.validate`.
5. Record failure pattern and fix in `kb/correction/` to prevent regressions.
6. Scale from single-query tests to dataset-level runs once targeted failures are resolved.

Notes:
- `run_agent.py` in our working DAB copy defaults to `--use_hints` enabled.
- OpenRouter is supported via `--llm openrouter/<provider>/<model>`.
- If provider connectivity is unstable, rerun with a new `--root_name` and check `final_agent.json` + `llm_calls.jsonl` before changing code.
- `DataAgentBench/` is intentionally ignored in this repo to avoid committing a full vendor clone.
- Fork-first means canonical runtime code lives in your DAB fork; this repo tracks KB, probes, and workflow docs.

## If You Modify DAB Files

When contributors change files inside `DataAgentBench/`, use fork branches + PRs as the default workflow.

Required steps:
1. Create a feature branch in your DAB fork.
2. Make and validate DAB changes locally.
3. Commit and push to your fork, then open a PR to your fork `main` (or release branch).
4. Record the fork URL + branch/commit in this repo docs when needed for reproducibility.
5. Commit only repo files here (`README.md`, KB/probes/docs/scripts), not `DataAgentBench/`.

Optional (for users not using your fork): refresh patch artifacts in this repo:
```powershell
.\scripts\refresh_dab_patch.ps1 -DabPath .\DataAgentBench
```
Then verify:
```powershell
.\scripts\verify_dab_patch.ps1 -DabPath .\DataAgentBench
```

If users already have local edits in `DataAgentBench/`, they should commit/stash/revert them before applying `dab-setup.patch`.

## Session Start — Document Load Order

Inject these files at the start of every agent session:

1. `architecture/memory.md`
2. `architecture/conductor_worker_pattern.md`
3. `architecture/openai_layers.md`
4. `correction/failure_log.md`
5. `correction/resolved_patterns.md`

Then load on demand:

- `domain/databases/<db>_schemas.md` for each database type in the query
- `domain/joins/join_key_mappings.md` for any cross-database join
- `domain/domain_terms/business_glossary.md` for telecom / Yelp / healthcare queries

## Adding a KB Document

1. Create the file in the appropriate `kb/` subdirectory
2. Add a test case to `EXPECTED_ANSWERS` in `kb/injection_test.py`
3. Run `python kb/injection_test.py --test-single <path> --verbose`
4. Revise until the test passes, then add a `CHANGELOG.md` entry

## Attribution

- Three-layer memory + autoDream — Claude Code architecture (March 2026)
- Six-layer context — OpenAI data agent writeup (Jan 2026)
- Injection test methodology — Andrej Karpathy
- Domain requirements — UC Berkeley DAB benchmark
