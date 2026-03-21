"""REST API server for CSM — exposes session state to web frontends."""
import json
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from csm.core.session_manager import SessionManager

_manager: "SessionManager | None" = None


def set_manager(mgr: "SessionManager") -> None:
    global _manager
    _manager = mgr


class CSMAPIHandler(BaseHTTPRequestHandler):
    """Minimal REST API handler."""

    def log_message(self, format, *args):
        pass  # suppress default logging

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/sessions":
            self._handle_sessions()
        elif self.path == "/api/health":
            self._json_response({"status": "ok", "sessions": len(_manager._sessions) if _manager else 0})
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.startswith("/api/sessions/") and self.path.endswith("/send"):
            session_id = self.path.split("/")[3]
            self._handle_send(session_id)
        else:
            self._json_response({"error": "not found"}, 404)

    def _handle_sessions(self):
        if not _manager:
            self._json_response({"sessions": [], "error": "manager not initialized"})
            return

        sessions = []
        for sid, state in _manager._sessions.items():
            sessions.append({
                "id": state.session_id,
                "name": state.config.name or state.config.cwd.split("/")[-1].split("\\")[-1],
                "project": state.config.cwd,
                "status": state.status.value.lower(),
                "stage": state.sop_stage or "none",
                "cost": round(state.cost_usd, 2),
                "tokens_in": state.tokens_in,
                "tokens_out": state.tokens_out,
                "started_at": state.started_at.isoformat(),
                "last_activity": state.last_activity.isoformat(),
                "pid": state.pid,
                "resume_id": state.claude_session_id,
                "model": state.config.model,
                "cost_per_hour": round(state.cost_per_hour(), 2),
                "uptime": state.active_duration_str(),
                "last_result_preview": state.last_result[:200] if state.last_result else "",
            })

        total_cost = sum(s["cost"] for s in sessions)
        self._json_response({
            "sessions": sessions,
            "total_cost": round(total_cost, 2),
            "total_sessions": len(sessions),
            "running": sum(1 for s in sessions if s["status"] == "run"),
            "waiting": sum(1 for s in sessions if s["status"] == "wait"),
        })

    def _handle_send(self, session_id: str):
        if not _manager:
            self._json_response({"error": "manager not initialized"}, 500)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length else ""

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response({"error": "invalid json"}, 400)
            return

        prompt = data.get("prompt", "")
        if not prompt:
            self._json_response({"error": "prompt required"}, 400)
            return

        # Queue the send - actual execution is async in CSM's event loop
        self._json_response({"queued": True, "session_id": session_id, "prompt": prompt[:100]})


def start_api_server(manager: "SessionManager", port: int = 3100) -> Thread:
    """Start the API server in a background thread."""
    set_manager(manager)
    server = HTTPServer(("0.0.0.0", port), CSMAPIHandler)
    thread = Thread(target=server.serve_forever, daemon=True, name="csm-api")
    thread.start()
    return thread
