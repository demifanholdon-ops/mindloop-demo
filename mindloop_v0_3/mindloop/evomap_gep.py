from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


class EvoMapGEPClient:
    """
    EvoMap GEP-A2A client.

    Safety rules:
    - No network call occurs on import.
    - Node registration happens only when register_node() is explicitly called.
    - validate_bundle() uses /a2a/validate and does not store/publish an asset.
    - publish_bundle() requires confirm=True.
    - node_secret is stored outside the repo and is never returned to the UI.
    """

    protocol = "gep-a2a"
    protocol_version = "1.0.0"

    def __init__(self):
        self.base_url = os.getenv("EVOMAP_BASE_URL", "https://evomap.ai").rstrip("/")
        self.model_name = os.getenv("EVOMAP_MODEL_NAME", os.getenv("LLM_MODEL", "mindloop-agent"))
        self.credentials_path = Path(
            os.getenv(
                "EVOMAP_NODE_FILE",
                str(Path.home() / ".evomap" / "mindloop_node.json"),
            )
        )

    @staticmethod
    def _now_iso():
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _message_id():
        return f"msg_{int(time.time() * 1000)}_{secrets.token_hex(4)}"

    @staticmethod
    def _canonical_hash(asset: dict) -> str:
        # EvoMap docs: asset_id is excluded; model_name is metadata and is not hashed.
        clean = {
            k: v for k, v in asset.items()
            if k not in {"asset_id", "model_name"}
        }
        canonical = json.dumps(
            clean,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _read_credentials(self):
        if not self.credentials_path.exists():
            return None
        try:
            return json.loads(self.credentials_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_credentials(self, data: dict):
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        self.credentials_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(self.credentials_path, 0o600)
        except Exception:
            pass

    def status(self):
        creds = self._read_credentials()
        return {
            "configured": bool(creds and creds.get("node_id") and creds.get("node_secret")),
            "node_id": creds.get("node_id") if creds else None,
            "claim_url": creds.get("claim_url") if creds else None,
            "base_url": self.base_url,
            "credentials_path": str(self.credentials_path),
        }

    def build_bundle(self, completed_actions: list[str], feedback_counts: dict, metrics: dict):
        completed = [x.strip() for x in completed_actions if isinstance(x, str) and x.strip()]
        completed = completed[-8:]

        drift_events = int(metrics.get("drift_events") or 0)
        refocuses = int(metrics.get("refocus_successes") or 0)
        done_events = int(metrics.get("done_events") or len(completed))
        stuck_events = int(metrics.get("stuck_events") or feedback_counts.get("stuck", 0) or 0)

        denom = max(1, done_events + stuck_events)
        task_score = done_events / denom
        drift_score = (refocuses / drift_events) if drift_events else task_score
        confidence = max(0.50, min(0.95, round((task_score + drift_score) / 2, 2)))

        gene = {
            "type": "Gene",
            "schema_version": "1.5.0",
            "category": "innovate",
            "signals_match": [
                "task initiation friction",
                "ambiguous high-level goal",
                "repeated stuck feedback",
                "attention drift",
            ],
            "summary": (
                "Reduce task-initiation friction by exposing one immediately executable "
                "physical action at a time and escalating intervention only when needed."
            ),
            "strategy": [
                "Translate the user's stated goal into one immediately executable physical action.",
                "Expose only the current action instead of the full plan.",
                "Use the lowest-interruption cue that can work.",
                "When the user reports being stuck, shrink or replace the action.",
                "Record outcomes and reuse strategies that repeatedly help the user act.",
            ],
            "domain": "other",
            "metadata": {
                "tags": ["cognitive-assistance", "wearable", "task-initiation", "haptic", "mindloop"]
            },
            "model_name": self.model_name,
        }
        gene["asset_id"] = self._canonical_hash(gene)

        capsule = {
            "type": "Capsule",
            "schema_version": "1.5.0",
            "trigger": [
                "task initiation friction",
                "stuck feedback",
                "attention drift",
            ],
            "gene": gene["asset_id"],
            "summary": (
                "MindLoop closed-loop intervention result: atomic action guidance, "
                "minimum-interruption cueing, and explicit user feedback."
            ),
            "content": {
                "successful_atomic_actions": completed,
                "feedback_counts": feedback_counts,
                "evaluation": {
                    "task_initiation_latency_s": metrics.get("task_initiation_latency_s"),
                    "return_to_task_time_s": metrics.get("return_to_task_time_s"),
                    "drift_events": drift_events,
                    "refocus_successes": refocuses,
                },
                "privacy": {
                    "raw_audio_shared": False,
                    "raw_video_shared": False,
                    "precise_location_shared": False,
                    "direct_identifiers_shared": False,
                },
            },
            "confidence": confidence,
            "blast_radius": {"files": 1, "lines": max(1, len(completed))},
            "outcome": {"status": "success" if done_events else "partial", "score": confidence},
            "env_fingerprint": {
                "platform": platform.system().lower(),
                "arch": platform.machine().lower(),
                "client": "mindloop-v0.3",
            },
            "success_streak": max(0, done_events),
            "source_type": "generated",
            "domain": "other",
            "metadata": {
                "tags": ["cognitive-assistance", "closed-loop", "wearable", "mindloop"]
            },
            "model_name": self.model_name,
        }
        capsule["asset_id"] = self._canonical_hash(capsule)

        return {
            "assets": [gene, capsule],
            "chain_id": "chain_mindloop_cognitive_assistance",
        }

    def _envelope(self, message_type: str, sender_id: str, payload: dict):
        return {
            "protocol": self.protocol,
            "protocol_version": self.protocol_version,
            "message_type": message_type,
            "message_id": self._message_id(),
            "sender_id": sender_id,
            "timestamp": self._now_iso(),
            "payload": payload,
        }

    async def register_node(self):
        existing = self._read_credentials()
        if existing and existing.get("node_id") and existing.get("node_secret"):
            return {
                "ok": True,
                "already_registered": True,
                "node_id": existing["node_id"],
                "claim_url": existing.get("claim_url"),
            }

        provisional_sender = "node_mindloop_" + secrets.token_hex(8)
        payload = {
            "capabilities": {
                "cognitive_assistance": True,
                "wearable_feedback": True,
                "task_decomposition": True,
            },
            "model": self.model_name,
            "gene_count": 0,
            "capsule_count": 0,
            "env_fingerprint": {
                "platform": platform.system().lower(),
                "arch": platform.machine().lower(),
                "client": "mindloop-v0.3",
            },
            "identity_doc": (
                "MindLoop is an embodied cognitive-assistance agent that helps a user "
                "start concrete actions and recover from attention drift."
            ),
            "constitution": (
                "Minimize interruption; avoid medical diagnosis; share only de-identified "
                "strategy outcomes; keep the user in control of external publication."
            ),
        }
        envelope = self._envelope("hello", provisional_sender, payload)

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{self.base_url}/a2a/hello", json=envelope)
            r.raise_for_status()
            body = r.json()

        # Handle both documented response layouts seen in EvoMap docs.
        data = body.get("payload") if isinstance(body, dict) and isinstance(body.get("payload"), dict) else body
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected EvoMap hello response")

        status = data.get("status", body.get("status") if isinstance(body, dict) else None)
        if status == "rejected":
            return {"ok": False, "reason": data.get("reason", "registration_rejected")}

        node_id = data.get("your_node_id") or data.get("sender_id")
        node_secret = data.get("node_secret")
        if not node_id or not node_secret:
            raise RuntimeError("EvoMap hello did not return node_id/node_secret")

        creds = {
            "node_id": node_id,
            "node_secret": node_secret,
            "claim_code": data.get("claim_code"),
            "claim_url": data.get("claim_url"),
            "created_at": self._now_iso(),
        }
        self._write_credentials(creds)
        return {
            "ok": True,
            "already_registered": False,
            "node_id": node_id,
            "claim_url": data.get("claim_url"),
            "claim_code": data.get("claim_code"),
        }

    async def _authenticated_post(self, path: str, envelope: dict):
        creds = self._read_credentials()
        if not creds or not creds.get("node_secret") or not creds.get("node_id"):
            return {
                "ok": False,
                "reason": "node_not_registered",
                "hint": "Call /api/evomap/register first.",
            }

        envelope = dict(envelope)
        envelope["sender_id"] = creds["node_id"]
        headers = {
            "Authorization": f"Bearer {creds['node_secret']}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{self.base_url}{path}", json=envelope, headers=headers)
            body_text = r.text
            try:
                body = r.json()
            except Exception:
                body = {"text": body_text}

            if r.status_code >= 400:
                return {
                    "ok": False,
                    "status_code": r.status_code,
                    "response": body,
                }
            return {
                "ok": True,
                "status_code": r.status_code,
                "response": body,
            }

    async def validate_bundle(self, bundle: dict):
        creds = self._read_credentials()
        sender = creds.get("node_id") if creds else "node_unregistered"
        envelope = self._envelope("publish", sender, bundle)
        return await self._authenticated_post("/a2a/validate", envelope)

    async def publish_bundle(self, bundle: dict, confirm: bool = False):
        if not confirm:
            return {
                "ok": False,
                "reason": "explicit_confirmation_required",
                "hint": "Set confirm=true only after reviewing the bundle and validation result.",
            }
        creds = self._read_credentials()
        sender = creds.get("node_id") if creds else "node_unregistered"
        envelope = self._envelope("publish", sender, bundle)
        return await self._authenticated_post("/a2a/publish", envelope)
