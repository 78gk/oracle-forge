from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import httpx

from utils.routing_policy import (
    build_schema_routing_summary,
    first_instruction_line,
    normalize_routing_selection,
)
from utils.token_limiter import TokenLimiter

_logger = logging.getLogger(__name__)


class LLMRoutingFailed(RuntimeError):
    """OpenRouter routing failed or misconfigured; agent must not use heuristic fallback."""


@dataclass
class LLMGuidance:
    selected_databases: List[str]
    rationale: str
    query_hints: Dict[str, Any]
    model: str
    used_llm: bool


class OpenRouterRoutingReasoner:
    """
    Database routing uses **OpenRouter only** (no Groq). Any API or contract failure raises
    :class:`LLMRoutingFailed` — there is no keyword fallback.
    """

    def __init__(self, repo_root: Optional[Path] = None, token_limiter: Optional[TokenLimiter] = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        load_dotenv(self.repo_root / ".env", override=False)
        self.openrouter_api_key = self._clean_env("OPENROUTER_API_KEY")
        self.model_name = self._resolve_model_name()
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
        self.openrouter_site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
        self.openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()
        self.token_limiter = token_limiter or TokenLimiter()
        self.http_client = httpx.Client(timeout=40)

    def plan(self, question: str, available_databases: List[str], context: Dict[str, Any]) -> LLMGuidance:
        if not self.openrouter_api_key:
            raise LLMRoutingFailed(
                "OPENROUTER_API_KEY is missing or placeholder; routing requires a valid OpenRouter API key."
            )

        schema_metadata = context.get("schema_metadata") or {}
        narrow_q = str(context.get("user_question") or question)

        context_layers = context.get("context_layers", {})
        trimmed_layers = self.token_limiter.trim_context_layers(context_layers)
        bundle = (context.get("schema_bundle_json") or "")[:8000]
        routing_summary = build_schema_routing_summary(schema_metadata, available_databases)
        instruction_line = first_instruction_line(
            str(context.get("routing_question") or ""),
            narrow_q,
        )
        dataset_id = context.get("dataset_id")
        dp = context.get("dataset_playbook")
        dataset_playbook = dp if isinstance(dp, dict) else None
        prompt = self._build_prompt(
            question,
            available_databases,
            trimmed_layers,
            schema_bundle_snippet=bundle,
            dataset_id=dataset_id if isinstance(dataset_id, str) else None,
            schema_routing_summary=routing_summary,
            instruction_line=instruction_line,
            dataset_playbook=dataset_playbook,
        )
        prompt = self.token_limiter.truncate_text(prompt, self.token_limiter.max_prompt_tokens)

        try:
            payload = self._plan_with_openrouter(prompt)
        except LLMRoutingFailed:
            raise
        except Exception as exc:
            if os.getenv("ORACLE_FORGE_DEBUG_LLM_ROUTING", "").lower() in {"1", "true", "yes", "on"}:
                _logger.warning("OpenRouter routing failed: %s: %s", type(exc).__name__, exc)
            raise LLMRoutingFailed(f"OpenRouter request failed: {exc}") from exc

        if not isinstance(payload, dict) or not payload:
            raise LLMRoutingFailed("OpenRouter returned a non-object or empty JSON payload.")

        selected = payload.get("selected_databases", [])
        if not isinstance(selected, list):
            selected = []
        selected_norm = [str(item).strip().lower() for item in selected if str(item).strip()]
        avail_l = [d.lower() for d in available_databases]
        filtered = [db for db in selected_norm if db in avail_l]
        if not filtered:
            raise LLMRoutingFailed(
                "OpenRouter JSON did not list any selected_databases that match available_databases."
            )
        filtered = normalize_routing_selection(narrow_q, filtered, available_databases, schema_metadata)
        if not filtered:
            raise LLMRoutingFailed("Routing normalization yielded no databases after LLM selection.")

        rationale = str(payload.get("rationale", "LLM-guided routing."))[:500]
        return LLMGuidance(
            selected_databases=filtered,
            rationale=rationale,
            query_hints=payload.get("query_hints", {}) if isinstance(payload.get("query_hints", {}), dict) else {},
            model=self.model_name,
            used_llm=True,
        )

    def _plan_with_openrouter(self, prompt: str) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name

        body = {
            "model": self.model_name,
            "temperature": 0,
            "max_tokens": 320,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a database routing and query planning assistant for a multi-DB data agent. "
                        "Return strict JSON with keys: selected_databases, rationale, query_hints. "
                        "Prefer the smallest set of databases: use ONE engine unless the task clearly needs "
                        "joining across systems or both relational SQL and document data. "
                        "Ground choices in the schema routing summary (table/collection names per engine)."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        response = self.http_client.post(f"{self.openrouter_base_url}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMRoutingFailed("OpenRouter returned no choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "{}")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        parsed = self._parse_json_content(str(content).strip())
        if not isinstance(parsed, dict):
            raise LLMRoutingFailed("OpenRouter message content was not a JSON object.")
        return parsed

    @staticmethod
    def _parse_json_content(content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise LLMRoutingFailed(f"OpenRouter returned invalid JSON: {exc}") from exc
        return parsed if isinstance(parsed, dict) else {}

    def _resolve_model_name(self) -> str:
        configured = os.getenv("MODEL_NAME", "").strip()
        if configured:
            return configured
        return "openai/gpt-4o-mini"

    @staticmethod
    def _clean_env(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            return ""
        lowered = value.lower()
        if lowered in {"your_api_key_here", "your_key_here", "changeme"}:
            return ""
        if lowered.startswith("your_") and ("_key_here" in lowered or "_api_key_here" in lowered):
            return ""
        return value

    def _build_prompt(
        self,
        question: str,
        available_databases: List[str],
        context_layers: Dict[str, Any],
        schema_bundle_snippet: str = "",
        dataset_id: Optional[str] = None,
        schema_routing_summary: str = "",
        instruction_line: str = "",
        dataset_playbook: Optional[Dict[str, Any]] = None,
    ) -> str:
        context_json = json.dumps(context_layers, ensure_ascii=False)[:8000]
        playbook_block = ""
        if isinstance(dataset_playbook, dict) and (dataset_playbook.get("summary") or "").strip():
            suggest = dataset_playbook.get("suggest_engines_order") or []
            sug_txt = ", ".join(str(x) for x in suggest[:12]) if suggest else ""
            playbook_block = (
                "BENCHMARK PLAYBOOK (dataset intent — use to choose engines and cross-DB work):\n"
                f"{str(dataset_playbook.get('summary', ''))[:4500]}\n"
                + (f"Suggested engine priority: {sug_txt}\n" if sug_txt else "")
                + "\n"
            )
        primary = ""
        if schema_bundle_snippet.strip():
            primary = (
                "PRIMARY schema bundle (authoritative table/collection names and fields — prefer routing to "
                "engines that have relevant objects listed here):\n"
                f"{schema_bundle_snippet}\n\n"
            )
        summary_block = ""
        if schema_routing_summary.strip():
            summary_block = (
                "Schema routing summary (non-empty engines — use for evidence in rationale):\n"
                f"{schema_routing_summary}\n\n"
            )
        ds_line = f"Dataset id (benchmark scope): {dataset_id}\n" if dataset_id else ""
        task_line = f"Task focus (first line): {instruction_line}\n" if instruction_line else ""
        return (
            f"{playbook_block}{primary}{summary_block}{ds_line}{task_line}"
            f"Question: {question}\n"
            f"Available databases: {available_databases}\n"
            "Use the schema summary and bundle to choose the minimum set of databases (prefer one unless "
            "cross-engine work is clearly required).\n"
            "Supporting context layers (trimmed):\n"
            f"{context_json}\n"
            "Return JSON only with keys: selected_databases, rationale, query_hints."
        )


# Backward-compatible alias for imports and docs.
GroqLlamaReasoner = OpenRouterRoutingReasoner
