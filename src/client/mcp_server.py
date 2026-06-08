"""MCP stdio server — exposes AIMS skills as MCP tools.

Reads JSON-RPC requests from stdin, writes responses to stdout.
Implements the Model Context Protocol for AI client integration
(Claude Code, Cursor, etc.).

Protocol:
  - initialize        — capability negotiation
  - tools/list         — list available skills as tools
  - tools/call         — execute a skill by name with arguments
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── JSON-RPC helpers ─────────────────────────────────────────────────────────


def _rpc_error(id: Any, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})


def _rpc_result(id: Any, result: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id, "result": result})


def _rpc_notification(method: str, params: Any = None) -> str:
    msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


# ── Server implementation ────────────────────────────────────────────────────


class McpServer:
    """MCP stdio server backed by SkillRegistry + WorkflowEngine."""

    def __init__(self) -> None:
        from src.skills.registry import SkillRegistry
        from src.runtime.sandbox import WorkflowEngine, resolve_impl

        self._registry = SkillRegistry()
        self._engine = WorkflowEngine(resolve_impl)
        self._initialized = False

    # ── Protocol handlers ──────────────────────────────────────────────────

    def handle_initialize(self, req_id: Any) -> str:
        """Initialize the session — required first handshake."""
        self._initialized = True
        return _rpc_result(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},  # we support tools
            },
            "serverInfo": {
                "name": "aims-mcp",
                "version": "1.0.0",
            },
        })

    def handle_list_tools(self, req_id: Any) -> str:
        """List all active skills as MCP tool definitions."""
        manifests = self._registry.get_all_manifests()
        tools = []
        for m in manifests:
            tools.append({
                "name": m.name,
                "description": m.description,
                "inputSchema": m.input_schema,
            })

        logger.info("MCP tools/list → %d tools", len(tools))
        return _rpc_result(req_id, {"tools": tools})

    def handle_call_tool(self, req_id: Any, params: Dict[str, Any]) -> str:
        """Execute a skill and return the result."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        manifest = self._registry.get(name)
        if manifest is None:
            return _rpc_error(req_id, -32602, f"Unknown skill: {name}")

        logger.info("MCP tools/call → %s  args=%s", name, arguments)
        try:
            receipt = self._engine.execute(manifest, arguments)
            if receipt.status == "SUCCESS":
                return _rpc_result(req_id, {
                    "content": [{"type": "text", "text": receipt.output}],
                })
            else:
                return _rpc_error(req_id, -32000, receipt.error_message)
        except Exception as exc:
            logger.error("MCP call_tool exception: %s", exc)
            return _rpc_error(req_id, -32000, f"{type(exc).__name__}: {exc}")

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """Read JSON-RPC requests from stdin and write responses to stdout."""
        logger.info("MCP server starting (stdio transport)")

        # Signal readiness to the host
        print(_rpc_notification("ready"), flush=True)

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                print(_rpc_error(None, -32700, f"Parse error: {exc}"), flush=True)
                continue

            req_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            try:
                if method == "initialize":
                    response = self.handle_initialize(req_id)
                elif method == "tools/list":
                    response = self.handle_list_tools(req_id)
                elif method == "tools/call":
                    response = self.handle_call_tool(req_id, params)
                elif method == "notifications/initialized":
                    response = ""  # no response needed
                else:
                    response = _rpc_error(
                        req_id, -32601, f"Method not found: {method}"
                    )
            except Exception as exc:
                logger.error("Unhandled error in %s: %s", method, exc)
                traceback.print_exc()
                response = _rpc_error(
                    req_id, -32000, f"Server error: {type(exc).__name__}: {exc}"
                )

            if response:
                print(response, flush=True)


def main() -> None:
    """Entry point for ``aims mcp``."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    server = McpServer()
    server.run()


if __name__ == "__main__":
    main()
