from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from utils.token_limiter import TokenLimiter

try:
    from groq import Groq
except Exception:  # pragma: no cover - optional runtime dependency
    Groq = None  # type: ignore[assignment]


@dataclass
class LLMGuidance:
    selected_databases: List[str]
    rationale: str
    query_hints: Dict[str, Any]
    model: str
    used_llm: bool


class GroqLlamaReasoner:
    def __init__(self, repo_root: Optional[Path] = None, token_limiter: Optional[TokenLimiter] = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        load_dotenv(self.repo_root / ".env")
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.model_name = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
        self.token_limiter = token_limiter or TokenLimiter()
        self.client = Groq(api_key=self.api_key) if self.api_key and Groq is not None else None

    def plan(self, question: str, available_databases: List[str], context: Dict[str, Any]) -> LLMGuidance:
        fallback = self._fallback(question, available_databases)
        if self.client is None:
            return fallback

        context_layers = context.get("context_layers", {})
        trimmed_layers = self.token_limiter.trim_context_layers(context_layers)
        prompt = self._build_prompt(question, available_databases, trimmed_layers)
        prompt = self.token_limiter.truncate_text(prompt, self.token_limiter.max_prompt_tokens)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                temperature=0,
                max_tokens=320,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a database routing and query planning assistant for a multi-DB data agent. "
                            "Return strict JSON with keys: selected_databases, rationale, query_hints."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = (response.choices[0].message.content or "{}").strip()
            payload = json.loads(content)
            selected = payload.get("selected_databases", [])
            if not isinstance(selected, list):
                selected = []
            selected_norm = [str(item).strip().lower() for item in selected if str(item).strip()]
            filtered = [db for db in selected_norm if db in [d.lower() for d in available_databases]]
            if not filtered:
                filtered = fallback.selected_databases
            return LLMGuidance(
                selected_databases=filtered,
                rationale=str(payload.get("rationale", "LLM-guided routing."))[:500],
                query_hints=payload.get("query_hints", {}) if isinstance(payload.get("query_hints", {}), dict) else {},
                model=self.model_name,
                used_llm=True,
            )
        except Exception:
            return fallback

    def _build_prompt(self, question: str, available_databases: List[str], context_layers: Dict[str, Any]) -> str:
        context_json = json.dumps(context_layers, ensure_ascii=False)[:12000]
        return (
            f"Question: {question}\n"
            f"Available databases: {available_databases}\n"
            "Use the provided context to choose database routes and query hints for each DB.\n"
            "Context layers (trimmed):\n"
            f"{context_json}\n"
            "Return JSON only."
        )

    def _fallback(self, question: str, available_databases: List[str]) -> LLMGuidance:
        question_l = question.lower()
        picks: List[str] = []
        for db in ["duckdb", "mongodb", "postgresql", "sqlite"]:
            if db in [d.lower() for d in available_databases] and db in question_l:
                picks.append(db)
        if not picks:
            for db in ["duckdb", "mongodb", "postgresql", "sqlite"]:
                if db in [d.lower() for d in available_databases]:
                    picks.append(db)
                    break
        if any(token in question_l for token in ["join", "across", "both", "combine"]) and "mongodb" in [d.lower() for d in available_databases]:
            if "mongodb" not in picks:
                picks.append("mongodb")
        return LLMGuidance(
            selected_databases=picks,
            rationale="Fallback routing used due unavailable LLM response.",
            query_hints={},
            model=self.model_name,
            used_llm=False,
        )

