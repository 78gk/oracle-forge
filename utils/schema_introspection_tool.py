"""Schema introspection tool with deterministic fallback support.

Primary mode:
- Use MCP tool metadata from `MCPToolsClient.get_schema_metadata()`.

Fallback mode:
- Parse `DataAgentBench/db_description.txt` for table/collection fields.
- Produce deterministic schema metadata when MCP/database services are unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SchemaObject:
    name: str
    fields: Dict[str, str]
    object_type: str  # "table" | "collection"


class SchemaIntrospectionTool:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self._cached: Dict[str, Any] = {}

    def collect(self, mcp_schema_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if mcp_schema_metadata:
            normalized = self._normalize_mcp_schema(mcp_schema_metadata)
            if normalized:
                self._cached = normalized
                return normalized
        fallback = self._from_dataagentbench_description()
        self._cached = fallback
        return fallback

    def _normalize_mcp_schema(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for raw_db, content in payload.items():
            db_name = str(raw_db).strip().lower()
            normalized.setdefault(db_name, {"tables": [], "collections": []})
            if not isinstance(content, dict):
                continue
            for key in ["tables", "collections"]:
                values = content.get(key, [])
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            normalized[db_name][key].append({"name": value, "fields": {}})
                        elif isinstance(value, dict):
                            normalized[db_name][key].append(
                                {
                                    "name": value.get("name", "unknown"),
                                    "fields": value.get("fields", {}) if isinstance(value.get("fields", {}), dict) else {},
                                }
                            )
        return normalized

    def _from_dataagentbench_description(self) -> Dict[str, Any]:
        desc_path = self.repo_root / "DataAgentBench" / "db_description.txt"
        if not desc_path.exists():
            return {
                "postgresql": {"tables": [{"name": "customers", "fields": {"customer_id": "INTEGER"}}], "collections": []},
                "mongodb": {"tables": [], "collections": [{"name": "business", "fields": {"business_id": "STRING"}}]},
                "sqlite": {"tables": [{"name": "records", "fields": {"id": "INTEGER"}}], "collections": []},
                "duckdb": {"tables": [{"name": "review", "fields": {"business_ref": "STRING"}}], "collections": []},
            }
        text = desc_path.read_text(encoding="utf-8", errors="ignore")
        chunks = self._extract_objects(text)
        metadata: Dict[str, Any] = {
            "postgresql": {"tables": [], "collections": []},
            "mongodb": {"tables": [], "collections": []},
            "sqlite": {"tables": [], "collections": []},
            "duckdb": {"tables": [], "collections": []},
        }
        for obj in chunks:
            if obj.object_type == "collection":
                metadata["mongodb"]["collections"].append({"name": obj.name, "fields": obj.fields})
            else:
                metadata["duckdb"]["tables"].append({"name": obj.name, "fields": obj.fields})
        if not metadata["postgresql"]["tables"]:
            metadata["postgresql"]["tables"] = [
                {"name": "business", "fields": {"business_id": "TEXT", "review_count": "INTEGER", "is_open": "INTEGER"}}
            ]
        if not metadata["sqlite"]["tables"]:
            metadata["sqlite"]["tables"] = [{"name": "user", "fields": {"user_id": "TEXT", "review_count": "INTEGER"}}]
        return metadata

    def _extract_objects(self, text: str) -> List[SchemaObject]:
        objects: List[SchemaObject] = []
        lines = text.splitlines()
        current_name: Optional[str] = None
        current_type: Optional[str] = None
        current_fields: Dict[str, str] = {}
        table_re = re.compile(r"^\s*-\s+([A-Za-z0-9_]+)\s*$")
        field_re = re.compile(r"^\s*-\s+([A-Za-z0-9_]+)\s+\(([^)]+)\)")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- This collection"):
                continue
            if stripped.startswith("- This table"):
                continue
            if stripped.startswith("- Fields:"):
                continue
            if stripped.startswith("-"):
                table_match = table_re.match(stripped)
                field_match = field_re.match(stripped)
                if field_match and current_name:
                    current_fields[field_match.group(1)] = field_match.group(2)
                elif table_match:
                    if current_name:
                        objects.append(
                            SchemaObject(
                                name=current_name,
                                fields=current_fields,
                                object_type=current_type or "table",
                            )
                        )
                    candidate = table_match.group(1)
                    current_name = candidate
                    current_fields = {}
                    current_type = "collection" if "collection" in text[max(0, text.find(candidate) - 200) : text.find(candidate)].lower() else "table"
        if current_name:
            objects.append(
                SchemaObject(
                    name=current_name,
                    fields=current_fields,
                    object_type=current_type or "table",
                )
            )
        return objects
