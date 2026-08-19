"""Nautobot job that triggers the agent's live-config backup endpoint.

This lets operators (or Celery beat) initiate a backup from Nautobot without
needing docker access inside the Nautobot container. The agent does the actual
config capture, drift comparison, git commit, and push.
"""
import os

import requests

from nautobot.apps.jobs import Job, StringVar, register_jobs

AGENT_URL = os.getenv("NAUTOBOT_AGENT_URL", "http://incident-agent:8000").rstrip("/")


class TriggerAgentBackup(Job):
    class Meta:
        name = "Trigger Agent Backup"
        description = "Ask the incident agent to back up live FRR configs to the golden-source repo"
        has_sensitive_variables = False

    targets = StringVar(
        description="Comma-separated hostnames (leave blank for all: core-rtr-01,edge-rtr-01,edge-rtr-02)",
        required=False,
        default="",
    )

    def run(self, targets=""):
        payload = {}
        if targets:
            payload["targets"] = [t.strip() for t in targets.split(",") if t.strip()]
        url = f"{AGENT_URL}/admin/backup"
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            self.logger.error("Agent backup request failed: %s", exc)
            raise

        data = resp.json()
        self.logger.info("Agent backup result: %s", data)
        return data


register_jobs(TriggerAgentBackup)
