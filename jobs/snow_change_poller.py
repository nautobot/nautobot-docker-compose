"""ServiceNow change-request poller Job.

Polls ServiceNow for approved change requests and enqueues each as a pending
approval in the incident-agent approval queue (shared Redis) for human
decision. Approval surfaces: agent UI (Chainlit) and the Nautobot "Approve
Snow Change" job.

Authentication uses the ServiceNow UI login flow (form POST to /login.do),
because basic-auth REST access is disabled on the target instance. The
established session (cookies) plus the CSRF token extracted from the UI
(g_ck) is used to call the Table API with an X-UserToken header.

Credentials come from environment variables:

    NAUTOBOT_SSOT_SNOW_URL
    NAUTOBOT_SSOT_SNOW_USERNAME
    NAUTOBOT_SSOT_SNOW_PASSWORD

The agent API base URL comes from:

    NAUTOBOT_AGENT_URL        (default http://incident-agent:8000)
"""

import json
import os
import re

import requests

from nautobot.apps.jobs import Job, register_jobs

CONFIG_PATH = "/opt/nautobot/jobs/integrations.json"


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

    def get_table(self, table, query="", fields="", limit=20):
        if not self.token:
            self.login()
        params = {"sysparm_limit": limit}
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = fields
        url = f"{self.base_url}/api/now/table/{table}"
        response = self.session.get(
            url,
            params=params,
            headers={"X-UserToken": self.token, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("result", [])


class SnowChangePoller(Job):
    class Meta:
        name = "ServiceNow Change Poller"
        description = "Poll ServiceNow for approved change requests (UI session auth) and enqueue approvals"
        has_sensitive_variables = False

    def run(self):
        base_url = os.getenv("NAUTOBOT_SSOT_SNOW_URL", "https://dev316890.service-now.com").rstrip("/")
        username = os.getenv("NAUTOBOT_SSOT_SNOW_USERNAME", "")
        password = os.getenv("NAUTOBOT_SSOT_SNOW_PASSWORD", "")
        agent_url = os.getenv("NAUTOBOT_AGENT_URL", "http://incident-agent:8000").rstrip("/")

        if not username or not password:
            if os.path.exists(CONFIG_PATH):
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
            self.logger.warning(
                "ServiceNow credentials not configured; set NAUTOBOT_SSOT_SNOW_USERNAME and "
                "NAUTOBOT_SSOT_SNOW_PASSWORD (or integrations.json)."
            )
            return

        try:
            client = ServiceNowSession(base_url, username, password).login()
        except Exception as exc:
            self.logger.error("ServiceNow login failed: %s", exc)
            return

        try:
            changes = client.get_table(
                "change_request",
                query="state=4",
                fields="number,sys_id,short_description,category,impact,state",
                limit=20,
            )
        except Exception as exc:
            self.logger.error("ServiceNow poll failed: %s", exc)
            return

        self.logger.info("found %d approved change request(s)", len(changes))
        if not changes:
            return

        existing_numbers = set()
        try:
            existing = requests.get(f"{agent_url}/approvals", timeout=30).json()
            for item in existing:
                action = item.get("action") or {}
                if action.get("type") == "snow_change" and action.get("number"):
                    existing_numbers.add(action["number"])
        except Exception as exc:
            self.logger.warning("could not read existing approvals from agent (%s); will enqueue all", exc)

        created = 0
        skipped = 0
        for change in changes:
            number = change.get("number", "")
            if number in existing_numbers:
                skipped += 1
                continue
            payload = {
                "description": change.get("short_description", number),
                "incident_id": "",
                "action": {
                    "type": "snow_change",
                    "number": number,
                    "sys_id": change.get("sys_id", ""),
                    "short_description": change.get("short_description", ""),
                    "state": change.get("state", ""),
                },
            }
            try:
                resp = requests.post(f"{agent_url}/approvals", json=payload, timeout=30)
                resp.raise_for_status()
                created += 1
            except Exception as exc:
                self.logger.error("failed to enqueue change %s: %s", number, exc)

        self.logger.info("enqueued %d approval(s), skipped %d already-known", created, skipped)


register_jobs(SnowChangePoller)