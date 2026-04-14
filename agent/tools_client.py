from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
import uuid

import httpx

from .utils import canonical_db_name, classify_failure, result_summary, sanitize_error


class MCPToolsClient:
    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        mock_mode: bool = False,
        allow_fallback_to_mock: bool = False,
        timeout_seconds: int = 12,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mock_mode = mock_mode
        self.allow_fallback_to_mock = allow_fallback_to_mock
        self.timeout_seconds = timeout_seconds
        self.discovered_tools: List[Dict[str, Any]] = []
        self.server_reachable = False
        self.duckdb_path = os.getenv("DUCKDB_PATH", "").strip()
        self.client = httpx.Client(timeout=self.timeout_seconds)

    def discover_tools(self) -> List[Dict[str, Any]]:
        if self.mock_mode:
            self.discovered_tools = self._mock_tools_catalog()
            return self.discovered_tools
        endpoint = f"{self.base_url}/mcp"
        try:
            payload = self._mcp_post("tools/list", {})
            tools = payload.get("tools", [])
            self.discovered_tools = [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []
            self._inject_local_duckdb_tool()
            self.server_reachable = True
            return self.discovered_tools
        except Exception as exc:
            try:
                # Backward compatibility for older Toolbox REST endpoints.
                fallback_endpoint = f"{self.base_url}/v1/tools"
                response = self.client.get(fallback_endpoint)
                response.raise_for_status()
                payload = response.json()
                tools = payload.get("tools", payload if isinstance(payload, list) else [])
                if not isinstance(tools, list):
                    tools = []
                self.discovered_tools = [tool for tool in tools if isinstance(tool, dict)]
                self._inject_local_duckdb_tool()
                self.server_reachable = True
                return self.discovered_tools
            except Exception:
                self.server_reachable = False
                if self.allow_fallback_to_mock:
                    self.mock_mode = True
                    self.discovered_tools = self._mock_tools_catalog()
                    return self.discovered_tools
                raise RuntimeError(
                    f"MCP server unreachable at {endpoint}. "
                    f"Set ORACLE_FORGE_MOCK_MODE=true for explicit mock mode, "
                    f"or ORACLE_FORGE_ALLOW_MOCK_FALLBACK=true to allow automatic fallback. "
                    f"Original error: {type(exc).__name__}: {exc}"
                ) from exc

    def get_schema_metadata(self) -> Dict[str, Any]:
        if self.mock_mode:
            return self._mock_schema_metadata()
        if not self.discovered_tools:
            self.discover_tools()
        metadata: Dict[str, Any] = {}
        schema_tools = [
            tool
            for tool in self.discovered_tools
            if any(
                token in f"{tool.get('name', '')} {tool.get('description', '')}".lower()
                for token in ["schema", "describe", "introspect", "collection", "table", "metadata"]
            )
        ]
        for tool in schema_tools:
            result = self._invoke_live(tool.get("name", ""), {"operation": "schema_discovery"})
            if not result.get("ok"):
                continue
            data = result.get("data")
            parsed = self._parse_schema_payload(data)
            for db_name, content in parsed.items():
                db = canonical_db_name(db_name)
                metadata.setdefault(db, {"tables": [], "collections": []})
                for key in ["tables", "collections"]:
                    for item in content.get(key, []):
                        if item not in metadata[db][key]:
                            metadata[db][key].append(item)
        bootstrap = self._bootstrap_schema_metadata()
        self._merge_schema_metadata(metadata, bootstrap)
        return metadata

    def select_tool(self, database: str, dialect: str) -> Optional[str]:
        if not self.discovered_tools:
            self.discover_tools()
        db = canonical_db_name(database)
        if not db:
            return None

        preferred_names = {
            "postgresql": ["postgres_sql_query"],
            "mongodb": ["mongodb_aggregate_business", "mongodb_aggregate_checkin"],
            "sqlite": ["sqlite_sql_query"],
            "duckdb": ["duckdb_sql_query", "local_duckdb_sql_query"],
        }
        for preferred in preferred_names.get(db, []):
            for tool in self.discovered_tools:
                if str(tool.get("name", "")) == preferred:
                    return preferred

        best_name = None
        best_score = float("-inf")
        for tool in self.discovered_tools:
            name = str(tool.get("name", ""))
            desc = str(tool.get("description", ""))
            combined = f"{name} {desc}".lower()
            score = 0
            if db == "mongodb":
                if any(token in combined for token in ["mongo", "aggregation", "pipeline"]):
                    score += 10
                if any(token in combined for token in ["postgres", "sqlite", "duckdb"]):
                    score -= 10
            elif db == "postgresql":
                if "postgres" in combined:
                    score += 10
                if any(token in combined for token in ["mongo", "sqlite", "duckdb"]):
                    score -= 10
            elif db == "sqlite":
                if "sqlite" in combined:
                    score += 10
                if any(token in combined for token in ["mongo", "postgres", "duckdb"]):
                    score -= 10
            elif db == "duckdb":
                if "duckdb" in combined:
                    score += 10
                if any(token in combined for token in ["mongo", "postgres", "sqlite"]):
                    score -= 10

            if dialect == "mongodb_aggregation":
                if "mongo" in combined:
                    score += 4
                if "sql" in combined:
                    score -= 6
            if dialect == "sql":
                if "sql" in combined:
                    score += 3
                if "aggregation" in combined:
                    score -= 6

            if score > best_score:
                best_score = score
                best_name = name
        if best_score < 1:
            return None
        return best_name

    def execute_with_retry(
        self,
        tool_name: str,
        payload: Dict[str, Any],
        selection_reason: str,
        dialect_handling: str,
        trace: List[Dict[str, Any]],
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        attempts = 0
        latest_error: Optional[Dict[str, Any]] = None
        current_payload = dict(payload)
        while attempts <= max_retries:
            attempts += 1
            outcome = self.invoke_tool(tool_name, current_payload, selection_reason, dialect_handling, trace)
            if outcome.get("ok"):
                outcome["attempts"] = attempts
                return outcome
            latest_error = outcome
            current_payload = self._repair_payload(current_payload)
        return {
            "ok": False,
            "error": latest_error.get("error", "Unknown tool failure") if latest_error else "Unknown tool failure",
            "error_type": classify_failure(latest_error.get("error", ""), payload) if latest_error else "unknown_error",
            "sanitized_error": sanitize_error(latest_error.get("error", "")) if latest_error else "Execution failed.",
            "tool": tool_name,
            "failed_query": payload.get("sql") or payload.get("pipeline") or "",
            "attempts": attempts,
        }

    def invoke_tool(
        self,
        tool_name: str,
        payload: Dict[str, Any],
        selection_reason: str,
        dialect_handling: str,
        trace: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        started = time.time()
        response = self._mock_invoke_tool(tool_name, payload) if self.mock_mode else self._invoke_live(tool_name, payload)
        duration_ms = int((time.time() - started) * 1000)
        trace.append(
            {
                "tool_used": tool_name,
                "selection_reason": selection_reason,
                "dialect_handling": dialect_handling,
                "raw_query": payload.get("sql") or payload.get("pipeline") or "",
                "result_summary": result_summary(response.get("data") if response.get("ok") else sanitize_error(response.get("error", ""))),
                "duration_ms": duration_ms,
                "success": bool(response.get("ok")),
                "failure_type": None if response.get("ok") else classify_failure(response.get("error", ""), payload),
            }
        )
        if response.get("ok"):
            return response
        return {
            "ok": False,
            "error": response.get("error", "Tool invocation failed"),
            "error_type": classify_failure(response.get("error", ""), payload),
            "sanitized_error": sanitize_error(response.get("error", "")),
            "tool": tool_name,
            "failed_query": payload.get("sql") or payload.get("pipeline") or "",
        }

    def _invoke_live(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "local_duckdb_sql_query":
            return self._invoke_local_duckdb(payload)

        prepared_payload = dict(payload)
        if "pipeline" in prepared_payload and "pipeline_json" not in prepared_payload:
            try:
                prepared_payload["pipeline_json"] = json.dumps(prepared_payload["pipeline"])
            except Exception:
                pass

        # Preferred path: MCP JSON-RPC over HTTP endpoint (/mcp).
        try:
            result = self._mcp_post("tools/call", {"name": tool_name, "arguments": prepared_payload})
            if result.get("isError"):
                return {"ok": False, "error": self._extract_mcp_error(result)}
            return {"ok": True, "data": self._parse_mcp_tool_result(result)}
        except Exception:
            pass

        # Backward compatibility for legacy REST endpoints.
        endpoint_variants = [
            f"{self.base_url}/v1/tools/{tool_name}:invoke",
            f"{self.base_url}/v1/tools/{tool_name}/invoke",
            f"{self.base_url}/v1/tools/invoke",
        ]
        body_variants = [
            {"arguments": prepared_payload},
            {"input": prepared_payload},
            {"tool": tool_name, "arguments": prepared_payload},
        ]
        last_error = "Unknown invocation error"
        for endpoint in endpoint_variants:
            for body in body_variants:
                try:
                    response = self.client.post(endpoint, json=body)
                    response.raise_for_status()
                    parsed = response.json()
                    return {"ok": True, "data": parsed}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "error": last_error}

    def _mcp_post(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/mcp"
        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        response = self.client.post(endpoint, json=request_body)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        if not isinstance(payload, dict) or "result" not in payload:
            raise RuntimeError(f"Unexpected MCP response shape: {payload}")
        result = payload.get("result", {})
        if not isinstance(result, dict):
            return {"value": result}
        return result

    def _parse_mcp_tool_result(self, result: Dict[str, Any]) -> Any:
        content = result.get("content")
        if not isinstance(content, list):
            return result

        parsed_items: List[Any] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue
            try:
                parsed_items.append(json.loads(text))
            except Exception:
                parsed_items.append(text)

        if not parsed_items:
            return result
        if len(parsed_items) == 1:
            single = parsed_items[0]
            if isinstance(single, dict):
                return [single]
            return single
        return parsed_items

    def _extract_mcp_error(self, result: Dict[str, Any]) -> str:
        content = result.get("content")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"].strip())
            if parts:
                return " | ".join(part for part in parts if part)
        return "Tool execution failed."

    def _repair_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        repaired = {}
        for key, value in payload.items():
            if isinstance(value, str):
                repaired[key] = value.strip()
            elif isinstance(value, list):
                repaired[key] = value
            else:
                repaired[key] = value
        return repaired

    def _parse_schema_payload(self, payload: Any) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        if isinstance(payload, dict):
            for db_name, raw in payload.items():
                db = canonical_db_name(db_name)
                metadata.setdefault(db, {"tables": [], "collections": []})
                if isinstance(raw, dict):
                    for key in ["tables", "collections"]:
                        values = raw.get(key, [])
                        if isinstance(values, list):
                            metadata[db][key].extend(values)
        return metadata

    @staticmethod
    def _merge_schema_metadata(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for db_name, payload in source.items():
            db = canonical_db_name(db_name)
            target.setdefault(db, {"tables": [], "collections": []})
            if not isinstance(payload, dict):
                continue
            for key in ["tables", "collections"]:
                values = payload.get(key, [])
                if not isinstance(values, list):
                    continue
                for value in values:
                    if value not in target[db][key]:
                        target[db][key].append(value)

    def _bootstrap_schema_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for tool in self.discovered_tools:
            tool_name = str(tool.get("name", ""))
            name_l = tool_name.lower()
            if not tool_name:
                continue

            if "mongodb_aggregate_" in name_l:
                collection = name_l.split("mongodb_aggregate_", 1)[1].strip()
                if collection:
                    metadata.setdefault("mongodb", {"tables": [], "collections": []})
                    coll_entry = {"name": collection}
                    if coll_entry not in metadata["mongodb"]["collections"]:
                        metadata["mongodb"]["collections"].append(coll_entry)

            if "duckdb" in name_l and "sql" in name_l:
                tables = self._introspect_sql_tables(tool_name, "duckdb")
                if tables:
                    metadata.setdefault("duckdb", {"tables": [], "collections": []})
                    for table in tables:
                        entry = {"name": table}
                        if entry not in metadata["duckdb"]["tables"]:
                            metadata["duckdb"]["tables"].append(entry)

            if "sqlite" in name_l and "sql" in name_l:
                tables = self._introspect_sql_tables(tool_name, "sqlite")
                if tables:
                    metadata.setdefault("sqlite", {"tables": [], "collections": []})
                    for table in tables:
                        entry = {"name": table}
                        if entry not in metadata["sqlite"]["tables"]:
                            metadata["sqlite"]["tables"].append(entry)

            if "postgres" in name_l and "sql" in name_l:
                tables = self._introspect_sql_tables(tool_name, "postgresql")
                if tables:
                    metadata.setdefault("postgresql", {"tables": [], "collections": []})
                    for table in tables:
                        entry = {"name": table}
                        if entry not in metadata["postgresql"]["tables"]:
                            metadata["postgresql"]["tables"].append(entry)

        return metadata

    def _inject_local_duckdb_tool(self) -> None:
        if not self.duckdb_path:
            return
        existing_names = {str(tool.get("name", "")) for tool in self.discovered_tools if isinstance(tool, dict)}
        if any("duckdb" in name.lower() for name in existing_names):
            return
        self.discovered_tools.append(
            {
                "name": "local_duckdb_sql_query",
                "description": "Local DuckDB SQL execution fallback when MCP does not expose DuckDB.",
            }
        )

    def _invoke_local_duckdb(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        sql = str(payload.get("sql", "")).strip()
        if not sql:
            return {"ok": False, "error": "Missing SQL payload for local DuckDB execution."}
        if not self.duckdb_path:
            return {"ok": False, "error": "DUCKDB_PATH is not configured."}
        try:
            import duckdb  # type: ignore
        except Exception:
            return {"ok": False, "error": "duckdb package is not installed in the runtime environment."}

        try:
            conn = duckdb.connect(self.duckdb_path, read_only=True)
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            columns = [col[0] for col in (cursor.description or [])]
            conn.close()
            if not columns:
                return {"ok": True, "data": []}
            records = [dict(zip(columns, row)) for row in rows]
            return {"ok": True, "data": records}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _introspect_sql_tables(self, tool_name: str, db_name: str) -> List[str]:
        probes: List[str]
        db = canonical_db_name(db_name)
        if db == "sqlite":
            probes = ["SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"]
        elif db == "duckdb":
            probes = [
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name;",
                "SHOW TABLES;",
            ]
        else:
            probes = [
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;",
            ]

        for sql in probes:
            result = self._invoke_live(tool_name, {"sql": sql})
            if not result.get("ok"):
                continue
            rows = self._as_record_list(result.get("data"))
            table_names = self._extract_table_names(rows)
            if table_names:
                return table_names
        return []

    @staticmethod
    def _extract_table_names(rows: List[Dict[str, Any]]) -> List[str]:
        names: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidate = row.get("table_name")
            if candidate is None:
                candidate = row.get("name")
            if candidate is None and row:
                candidate = next(iter(row.values()))
            if isinstance(candidate, str):
                stripped = candidate.strip()
                if stripped and stripped not in names:
                    names.append(stripped)
        return names

    @staticmethod
    def _as_record_list(data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
        if isinstance(data, str):
            text = data.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                return []
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                return [parsed]
        return []

    def _mock_tools_catalog(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "postgres_primary_sql",
                "description": "PostgreSQL SQL execution tool for relational queries and joins.",
            },
            {
                "name": "mongodb_aggregate_pipeline",
                "description": "MongoDB aggregation pipeline executor for collections and nested fields.",
            },
            {
                "name": "sqlite_sql_runner",
                "description": "SQLite SQL execution tool for lightweight transaction datasets.",
            },
            {
                "name": "duckdb_sql_analytics",
                "description": "DuckDB SQL analytics execution for aggregations and window operations.",
            },
            {
                "name": "schema_discovery_global",
                "description": "Discover database schemas, table fields, and data types across configured connections.",
            },
        ]

    def _mock_schema_metadata(self) -> Dict[str, Any]:
        return {
            "postgresql": {
                "tables": [
                    {"name": "subscribers", "fields": {"subscriber_id": "INT", "monthly_revenue": "DECIMAL"}},
                    {"name": "business", "fields": {"business_id": "TEXT", "stars": "FLOAT"}},
                ],
                "collections": [],
            },
            "mongodb": {
                "tables": [],
                "collections": [
                    {"name": "support_tickets", "fields": {"customer_id": "STRING", "issue_description": "STRING", "ticket_count": "INT"}},
                    {"name": "subscribers", "fields": {"customer_id": "STRING", "plan_type": "STRING"}},
                ],
            },
            "sqlite": {
                "tables": [
                    {"name": "transactions", "fields": {"customer_id": "INTEGER", "amount": "REAL"}},
                ],
                "collections": [],
            },
            "duckdb": {
                "tables": [
                    {"name": "sales_fact", "fields": {"customer_id": "INTEGER", "total_sales": "DECIMAL"}},
                ],
                "collections": [],
            },
        }

    def _mock_invoke_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(payload.get("question", "")).lower()
        if payload.get("operation") == "schema_discovery":
            return {"ok": True, "data": self._mock_schema_metadata()}
        if "schema" in tool_name.lower() and "sql" not in tool_name.lower():
            return {"ok": True, "data": self._mock_schema_metadata()}
        if "force_error" in text:
            return {"ok": False, "error": "Forced mock error for validation path"}
        db = canonical_db_name(payload.get("database", ""))
        if db == "postgresql":
            return {
                "ok": True,
                "data": [
                    {"subscriber_id": 123, "monthly_revenue": 120.0, "plan_type": "postpaid"},
                    {"subscriber_id": 456, "monthly_revenue": 80.0, "plan_type": "prepaid"},
                ],
            }
        if db == "mongodb":
            return {
                "ok": True,
                "data": [
                    {
                        "customer_id": "CUST-123",
                        "ticket_count": 3,
                        "issue_description": "Customer is frustrated with service quality",
                    },
                    {
                        "customer_id": "CUST-456",
                        "ticket_count": 1,
                        "issue_description": "Customer says service is okay",
                    },
                ],
            }
        if db == "sqlite":
            return {
                "ok": True,
                "data": [
                    {"customer_id": 123, "amount": 220.5},
                    {"customer_id": 456, "amount": 80.0},
                ],
            }
        if db == "duckdb":
            return {
                "ok": True,
                "data": [
                    {"customer_id": 123, "total_sales": 1000.0},
                    {"customer_id": 456, "total_sales": 500.0},
                ],
            }
        return {"ok": False, "error": f"Unsupported mock database route for payload: {payload}"}
