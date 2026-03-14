"""
backend/mini_assistant/phase8/approval_store.py

In-memory store for tool executions that require user approval.
Each pending approval has a UUID, a status, and the full tool request.

Status lifecycle:  pending → approved → (executed by ToolBrain)
                   pending → denied
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


class ApprovalStore:
    def __init__(self):
        self._store: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_pending(
        self,
        tool_name: str,
        command: str,
        session_id: str,
        risk_level: str,
        reasons: List[str],
    ) -> str:
        approval_id = str(uuid.uuid4())
        self._store[approval_id] = {
            "id": approval_id,
            "tool_name": tool_name,
            "command": command,
            "session_id": session_id,
            "risk_level": risk_level,
            "reasons": reasons,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
        }
        return approval_id

    def mark_approved(self, approval_id: str) -> bool:
        if approval_id not in self._store:
            return False
        self._store[approval_id]["status"] = "approved"
        self._store[approval_id]["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def mark_denied(self, approval_id: str) -> bool:
        if approval_id not in self._store:
            return False
        self._store[approval_id]["status"] = "denied"
        self._store[approval_id]["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def mark_executed(self, approval_id: str) -> bool:
        if approval_id not in self._store:
            return False
        self._store[approval_id]["status"] = "executed"
        return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_pending(self, approval_id: str) -> Optional[dict]:
        entry = self._store.get(approval_id)
        if entry and entry["status"] in ("pending", "approved"):
            return entry
        return None

    def list_pending(self, session_id: Optional[str] = None) -> List[dict]:
        results = [
            e for e in self._store.values()
            if e["status"] == "pending"
        ]
        if session_id:
            results = [e for e in results if e["session_id"] == session_id]
        return sorted(results, key=lambda e: e["created_at"])

    def list_all(self, session_id: Optional[str] = None) -> List[dict]:
        results = list(self._store.values())
        if session_id:
            results = [e for e in results if e["session_id"] == session_id]
        return sorted(results, key=lambda e: e["created_at"], reverse=True)

    def get(self, approval_id: str) -> Optional[dict]:
        return self._store.get(approval_id)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_session(self, session_id: str) -> int:
        keys = [k for k, v in self._store.items() if v["session_id"] == session_id]
        for k in keys:
            del self._store[k]
        return len(keys)


# Singleton
approval_store = ApprovalStore()
