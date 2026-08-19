"""ServiceNow change approval bridge Jobs.

ApproveSnowChange: the Nautobot UI approval surface for pending ServiceNow
changes enqueued by the ServiceNow Change Poller into the incident-agent
approval queue. Leave the approval id empty to list pending changes, or
provide one to approve/reject it.

RecordSnowChange: audit trail job invoked by the agent when an approval is
decided from the agent UI, so Nautobot keeps a JobResult record of every
decision.

The agent API base URL comes from NAUTOBOT_AGENT_URL
(default http://incident-agent:8000).
"""

import json
import os

import requests

from nautobot.apps.jobs import BooleanVar, Job, JobButtonReceiver, TextVar, register_jobs

AGENT_URL = os.getenv("NAUTOBOT_AGENT_URL", "http://incident-agent:8000").rstrip("/")


class ApproveSnowChange(Job):
    class Meta:
        name = "Approve Snow Change"
        description = (
            "Approve or reject a pending ServiceNow change (agent approval queue). "
            "Leave approval id empty to list pending changes."
        )
        has_sensitive_variables = False

    approval_id = TextVar(description="Approval id to decide (empty = list pending)", required=False, default="")
    approved = BooleanVar(description="Approve the change?", default=True)

    def run(self, approval_id="", approved=True):
        try:
            pending = requests.get(f"{AGENT_URL}/approvals", params={"status": "pending"}, timeout=30).json()
        except Exception as exc:
            self.logger.error("could not reach agent approval queue: %s", exc)
            return

        snow_changes = [
            item
            for item in pending
            if (item.get("action") or {}).get("type") == "snow_change"
        ]
        if not snow_changes:
            self.logger.info("no pending ServiceNow changes")
            return

        if not approval_id:
            self.logger.info("%d pending ServiceNow change(s):", len(snow_changes))
            for item in snow_changes:
                number = (item.get("action") or {}).get("number", "")
                self.logger.info(
                    "  %s  [%s]  %s",
                    item.get("id"),
                    number,
                    item.get("description", ""),
                )
            return

        match = [item for item in snow_changes if item.get("id") == approval_id]
        if not match:
            self.logger.error("approval %s not found among pending changes", approval_id[:8])
            return

        try:
            resp = requests.post(
                f"{AGENT_URL}/approvals/{approval_id}/decide",
                json={"approved": bool(approved), "by": "nautobot-ui"},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            detail = resp.text if resp else str(exc)
            self.logger.error("decision failed: %s %s", exc, detail)
            return
        except Exception as exc:
            self.logger.error("decision failed: %s", exc)
            return

        result = resp.json().get("approval", {})
        self.logger.info(
            "change %s -> %s by %s",
            (result.get("action") or {}).get("number", approval_id[:8]),
            result.get("status"),
            result.get("decided_by"),
        )
        self.logger.info("result: %s", json.dumps(result, default=str))


class ApproveChange(Job):
    class Meta:
        name = "Approve Change"
        description = (
            "Approve or reject a pending change approval (ServiceNow or Nautobot-originated). "
            "Leave approval id empty to list pending changes."
        )
        has_sensitive_variables = False

    approval_id = TextVar(description="Approval id to decide (empty = list pending)", required=False, default="")
    approved = BooleanVar(description="Approve the change?", default=True)

    def run(self, approval_id="", approved=True):
        try:
            pending = requests.get(f"{AGENT_URL}/approvals", params={"status": "pending"}, timeout=30).json()
        except Exception as exc:
            self.logger.error("could not reach agent approval queue: %s", exc)
            return

        changes = [
            item
            for item in pending
            if (item.get("action") or {}).get("type") in ("snow_change", "nautobot_change")
        ]
        if not changes:
            self.logger.info("no pending change approvals")
            return

        if not approval_id:
            self.logger.info("%d pending change approval(s):", len(changes))
            for item in changes:
                action = item.get("action") or {}
                self.logger.info(
                    "  %s  [%s/%s]  %s",
                    item.get("id"),
                    action.get("type", ""),
                    action.get("number", ""),
                    item.get("description", "")[:80],
                )
            return

        match = [item for item in changes if item.get("id") == approval_id]
        if not match:
            self.logger.error("approval %s not found among pending changes", approval_id[:8])
            return

        try:
            resp = requests.post(
                f"{AGENT_URL}/approvals/{approval_id}/decide",
                json={"approved": bool(approved), "by": "nautobot-ui"},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            detail = resp.text if resp else str(exc)
            self.logger.error("decision failed: %s %s", exc, detail)
            return
        except Exception as exc:
            self.logger.error("decision failed: %s", exc)
            return

        result = resp.json().get("approval", {})
        action = result.get("action") or {}
        self.logger.info(
            "change %s/%s -> %s by %s",
            action.get("type", ""),
            action.get("number", approval_id[:8]),
            result.get("status"),
            result.get("decided_by"),
        )


def _decide_pending(logger, approval_id="", approved=True, auto=False):
    """List pending change approvals, or approve/reject one (shared by jobs and button receivers)."""
    try:
        pending = requests.get(f"{AGENT_URL}/approvals", params={"status": "pending"}, timeout=30).json()
    except Exception as exc:
        logger.error("could not reach agent approval queue: %s", exc)
        return

    changes = [
        item
        for item in pending
        if (item.get("action") or {}).get("type") in ("snow_change", "nautobot_change")
    ]
    if not changes:
        logger.info("no pending change approvals")
        return

    target = None
    if approval_id:
        target = next((item for item in changes if item.get("id") == approval_id), None)
        if not target:
            logger.error("approval %s not found among pending changes", approval_id[:8])
            return
    elif auto:
        target = max(changes, key=lambda item: item.get("created_at", ""))
        logger.info(
            "auto-deciding most recent pending approval %s [%s/%s]",
            target.get("id"),
            (target.get("action") or {}).get("type", ""),
            (target.get("action") or {}).get("number", ""),
        )

    if target is None:
        logger.info("%d pending change approval(s):", len(changes))
        for item in changes:
            action = item.get("action") or {}
            logger.info(
                "  %s  [%s/%s]  %s",
                item.get("id"),
                action.get("type", ""),
                action.get("number", ""),
                item.get("description", "")[:80],
            )
        return

    try:
        resp = requests.post(
            f"{AGENT_URL}/approvals/{target['id']}/decide",
            json={"approved": bool(approved), "by": "nautobot-ui"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        detail = resp.text if resp else str(exc)
        logger.error("decision failed: %s %s", exc, detail)
        return
    except Exception as exc:
        logger.error("decision failed: %s", exc)
        return

    result = resp.json().get("approval", {})
    action = result.get("action") or {}
    logger.info(
        "change %s/%s -> %s by %s",
        action.get("type", ""),
        action.get("number", target["id"][:8]),
        result.get("status"),
        result.get("decided_by"),
    )


class PendingApprovals(Job):
    class Meta:
        name = "Pending Approvals"
        description = (
            "List pending change approvals, or approve/reject one. "
            "approval_id empty lists; set auto to decide the most recent pending change."
        )
        has_sensitive_variables = False

    approval_id = TextVar(description="Approval id to decide (empty = list or auto)", required=False, default="")
    approved = BooleanVar(description="Approve the change?", default=True)
    auto = BooleanVar(
        description="When approval_id is empty, decide the most recent pending change",
        default=False,
    )

    def run(self, approval_id="", approved=True, auto=False):
        _decide_pending(self.logger, approval_id, approved, auto)


class ListPendingApprovalsButtonReceiver(JobButtonReceiver):
    class Meta:
        name = "List Pending Approvals"
        description = "Job Button receiver: list the pending change approvals."
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        _decide_pending(self.logger)


class ApproveLatestChangeButtonReceiver(JobButtonReceiver):
    class Meta:
        name = "Approve Latest Change"
        description = "Job Button receiver: approve the most recent pending change approval."
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        _decide_pending(self.logger, approved=True, auto=True)


class RejectLatestChangeButtonReceiver(JobButtonReceiver):
    class Meta:
        name = "Reject Latest Change"
        description = "Job Button receiver: reject the most recent pending change approval."
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        _decide_pending(self.logger, approved=False, auto=True)


class RecordSnowChange(Job):
    class Meta:
        name = "Record Snow Change"
        description = "Record an approved/rejected ServiceNow change decision in Nautobot (audit trail)"
        has_sensitive_variables = False

    change_number = TextVar(description="ServiceNow change number")
    description = TextVar(description="Short description", required=False, default="")
    decision = TextVar(description="approved or rejected", required=False, default="")
    approved_by = TextVar(description="Who decided", required=False, default="")

    def run(self, change_number, description="", decision="", approved_by=""):
        self.logger.info(
            "SNOW change %s decision=%s decided_by=%s description=%s",
            change_number,
            decision,
            approved_by,
            description,
        )


register_jobs(
    ApproveSnowChange,
    ApproveChange,
    PendingApprovals,
    ListPendingApprovalsButtonReceiver,
    ApproveLatestChangeButtonReceiver,
    RejectLatestChangeButtonReceiver,
    RecordSnowChange,
)