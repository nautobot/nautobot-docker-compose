"""ServiceNow incident reporting Job (Flow A write-back).

Creates/updates a ServiceNow incident for an agent incident. Idempotent: looks
up an existing incident by the built-in ``correlation_id`` field and PATCHes it
if found, otherwise creates it. This is the single owner of SNOW incident
records for the proactive pipeline, so no duplicates.

Uses the same UI login-flow auth as the change poller/update jobs.

Credentials come from environment variables:

    NAUTOBOT_SSOT_SNOW_URL
    NAUTOBOT_SSOT_SNOW_USERNAME
    NAUTOBOT_SSOT_SNOW_PASSWORD

Incident states: 1 = New, 2 = In Progress, 6 = Resolved, 7 = Closed.
"""

import json
import os
import re

import requests

from nautobot.apps.jobs import Job, TextVar, register_jobs

CONFIG_PATH = "/opt/nautobot/jobs/integrations.json"

STATE_MAP = {
    "New": "1",
    "In Progress": "2",
    "Resolved": "6",
    "Closed": "7",
    "Canceled": "7",
}


class ServiceNowSession:
    """Authenticate against ServiceNow via the UI login flow and call the Table API."""

    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token = None

    def login(self):
        login_url = f"{self.base_url}/login.do"
        response = self.session.get(login_url, timeout=30)
        response.raise_for_status()
        payload = {
            "user_name": self.username,
            "user_password": self.password,
            "sys_action": "sysverb_login",
            "ni.nolog.user_password": "true",
            "ni.noecho.user_name": "true",
            "ni.noecho.user_password": "true",
            "screensize": "1920x1080",
            "sysparm_referring_url": "login.do",
        }
        response = self.session.post(login_url, data=payload, timeout=30)
        response.raise_for_status()
        home = self.session.get(f"{self.base_url}/", timeout=30)
        home.raise_for_status()
        if "user_name" in home.text and "user_password" in home.text:
            raise RuntimeError("ServiceNow login failed: login form returned")
        match = re.search(r"g_ck\s*=\s*['\"]([^'\"]+)['\"]", home.text)
        if not match:
            raise RuntimeError("ServiceNow login succeeded but CSRF token (g_ck) not found")
        self.token = match.group(1)
        return self

    def _headers(self):
        return {"X-UserToken": self.token, "Accept": "application/json"}

    def get_table(self, table, query="", fields="", limit=20):
        if not self.token:
            self.login()
        params = {"sysparm_limit": limit}
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = fields
        url = f"{self.base_url}/api/now/table/{table}"
        response = self.session.get(url, params=params, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("result", [])

    def post_table(self, table, payload):
        if not self.token:
            self.login()
        url = f"{self.base_url}/api/now/table/{table}"
        response = self.session.post(url, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("result", {})

    def patch_table(self, table, sys_id, payload):
        if not self.token:
            self.login()
        url = f"{self.base_url}/api/now/table/{table}/{sys_id}"
        response = self.session.patch(url, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("result", {})


def _impact_urgency(severity):
    sev = (severity or "").lower()
    if sev in ("critical", "high"):
        return "1", "1"
    if sev in ("medium", "warning"):
        return "2", "2"
    return "3", "3"


class ReportSnowIncident(Job):
    class Meta:
        name = "Report Snow Incident"
        description = "Idempotent ServiceNow incident create/update for the proactive pipeline (Flow A)"
        has_sensitive_variables = False

    action = TextVar(description="action: upsert (default)", default="upsert")
    correlation_id = TextVar(description="Agent incident id used as SNOW correlation_id", default="")
    short_description = TextVar(description="Incident short description", default="")
    description = TextVar(description="Incident description", default="")
    severity = TextVar(description="Incident severity (critical/high/medium/warning/info)", default="medium")
    source = TextVar(description="Alert source (zabbix/nautobot_drift/...)", default="zabbix")
    state = TextVar(description="Desired state: In Progress / Resolved / Closed / Canceled", default="In Progress")
    resolution = TextVar(description="Resolution text (used when closing)", required=False, default="")

    def run(self, action="upsert", correlation_id="", short_description="", description="", severity="medium", source="zabbix", state="In Progress", resolution=""):
        base_url = os.getenv("NAUTOBOT_SSOT_SNOW_URL", "https://dev316890.service-now.com").rstrip("/")
        username = os.getenv("NAUTOBOT_SSOT_SNOW_USERNAME", "")
        password = os.getenv("NAUTOBOT_SSOT_SNOW_PASSWORD", "")

        if not username or not password and os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            snow = data.get("integrations", {}).get("ServiceNow", {})
            base_url = snow.get("url", base_url).rstrip("/")
            for secret_def in snow.get("secrets", []):
                if secret_def.get("secret_type") == "Username":
                    username = os.getenv(secret_def.get("env_var", ""), username)
                if secret_def.get("secret_type") == "Password":
                    password = os.getenv(secret_def.get("env_var", ""), password)

        if not username or not password:
            self.logger.warning("ServiceNow credentials not configured")
            return

        try:
            client = ServiceNowSession(base_url, username, password).login()
        except Exception as exc:
            self.logger.error("ServiceNow login failed: %s", exc)
            return

        impact, urgency = _impact_urgency(severity)
        target_state = STATE_MAP.get(state, "1")
        payload = {
            "short_description": short_description or f"[{source}] network alert",
            "description": description or short_description,
            "impact": impact,
            "urgency": urgency,
            "state": target_state,
            "correlation_id": correlation_id,
        }
        if state in ("Resolved", "Closed", "Canceled"):
            # ServiceNow incident table uses close_code, not resolution_code.
            payload["close_code"] = "Resolved by change"
            payload["close_notes"] = resolution or "Automated remediation completed"

        try:
            matches = client.get_table(
                "incident",
                query=f"correlation_id={correlation_id}",
                fields="sys_id,number,short_description,state",
                limit=5,
            )
        except Exception as exc:
            self.logger.error("ServiceNow incident lookup failed: %s", exc)
            return

        if matches:
            match = matches[0]
            try:
                result = client.patch_table("incident", match["sys_id"], payload)
            except Exception as exc:
                self.logger.error("ServiceNow incident update failed: %s", exc)
                return
            self.logger.info(
                "updated existing incident %s (%s) state=%s",
                result.get("number"),
                result.get("sys_id"),
                result.get("state"),
            )
            return result.get("sys_id")

        try:
            result = client.post_table("incident", payload)
        except Exception as exc:
            self.logger.error("ServiceNow incident create failed: %s", exc)
            return
        self.logger.info(
            "created incident %s (%s) correlation_id=%s state=%s",
            result.get("number"),
            result.get("sys_id"),
            correlation_id,
            result.get("state"),
        )
        return result.get("sys_id")


register_jobs(ReportSnowIncident)