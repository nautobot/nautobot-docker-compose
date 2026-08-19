"""ServiceNow change-request status write-back Job.

Updates the state of a ServiceNow change request (e.g. to 5 = Implemented)
after the CI/CD pipeline has completed. Uses the same UI session auth as the
change poller.

Credentials come from environment variables:

    NAUTOBOT_SSOT_SNOW_URL
    NAUTOBOT_SSOT_SNOW_USERNAME
    NAUTOBOT_SSOT_SNOW_PASSWORD

State values: 3 = Canceled, 4 = Scheduled, 5 = Implemented, 6 = Review,
7 = Closed.
"""

import json
import os
import re

import requests

from nautobot.apps.jobs import Job, TextVar, register_jobs

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

    def patch_table(self, table, sys_id, payload):
        if not self.token:
            self.login()
        url = f"{self.base_url}/api/now/table/{table}/{sys_id}"
        response = self.session.patch(url, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("result", {})

    def post_table(self, table, payload):
        if not self.token:
            self.login()
        url = f"{self.base_url}/api/now/table/{table}"
        response = self.session.post(url, json=payload, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("result", {})


class CreateSnowChange(Job):
    class Meta:
        name = "Create Snow Change"
        description = "Create a ServiceNow change request for an approved agent change"
        has_sensitive_variables = False

    correlation_id = TextVar(description="Agent incident id used as correlation_id", default="")
    short_description = TextVar(description="Change short description", default="")
    description = TextVar(description="Change description", default="")
    requested_by = TextVar(description="Who requested the change", required=False, default="NetOps Agent")
    assignment_group = TextVar(description="ServiceNow assignment group", required=False, default="Network Operations")
    priority = TextVar(description="Priority (1-4)", required=False, default="2")

    def run(self, correlation_id="", short_description="", description="", requested_by="NetOps Agent", assignment_group="Network Operations", priority="2"):
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

        payload = {
            "short_description": short_description or "Network change initiated by NetOps Agent",
            "description": description or short_description,
            "requested_by": requested_by,
            "assignment_group": assignment_group,
            "priority": priority,
            "correlation_id": correlation_id,
            "u_authorization_state": "Requested",
        }
        try:
            # Check if a change already exists for this correlation_id
            matches = client.get_table(
                "change_request",
                query=f"correlation_id={correlation_id}",
                fields="number,sys_id",
                limit=5,
            )
            if matches:
                result = client.patch_table("change_request", matches[0]["sys_id"], payload)
                self.logger.info("updated existing change %s", result.get("number"))
                return result.get("number")
            result = client.post_table("change_request", payload)
        except Exception as exc:
            self.logger.error("ServiceNow change create failed: %s", exc)
            return
        self.logger.info(
            "created change %s correlation_id=%s",
            result.get("number"),
            correlation_id,
        )
        return result.get("number")


class UpdateSnowChange(Job):
    class Meta:
        name = "Update Snow Change"
        description = "Update the state of a ServiceNow change request after implementation"
        has_sensitive_variables = False

    change_number = TextVar(description="ServiceNow change number (e.g. CHG0000002)")
    state = TextVar(
        description=(
            "Target state (3=Canceled, 4=Scheduled, 5=Implemented, 6=Review, 7=Closed). "
            "Note: change_request.state is workflow-controlled and a direct PATCH is usually ignored; "
            "the journal comment is the authoritative write-back."
        ),
        default="5",
    )
    notes = TextVar(description="Implementation notes to append", required=False, default="")

    def run(self, change_number, state="5", notes=""):
        base_url = os.getenv("NAUTOBOT_SSOT_SNOW_URL", "https://dev316890.service-now.com").rstrip("/")
        username = os.getenv("NAUTOBOT_SSOT_SNOW_USERNAME", "")
        password = os.getenv("NAUTOBOT_SSOT_SNOW_PASSWORD", "")

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
            self.logger.warning("ServiceNow credentials not configured")
            return

        try:
            client = ServiceNowSession(base_url, username, password).login()
            matches = client.get_table(
                "change_request",
                query=f"number={change_number}",
                fields="number,sys_id,state,short_description",
                limit=5,
            )
        except Exception as exc:
            self.logger.error("ServiceNow lookup failed: %s", exc)
            return

        if not matches:
            self.logger.error("change %s not found in ServiceNow", change_number)
            return

        match = matches[0]
        self.logger.info(
            "found %s state=%s desc=%s",
            match.get("number"),
            match.get("state"),
            match.get("short_description", ""),
        )

        if notes:
            journal = f"Nautobot: {notes}"
        else:
            journal = f"Nautobot: change marked for state {state} after CI/CD"
        try:
            result = client.patch_table("change_request", match["sys_id"], {"comments": journal})
        except Exception as exc:
            self.logger.error("ServiceNow update failed: %s", exc)
            return
        self.logger.info("journal comment appended to %s", change_number)

        try:
            check = client.get_table(
                "change_request",
                query=f"number={change_number}",
                fields="number,state",
                limit=5,
            )
        except Exception as exc:
            self.logger.warning("could not verify state after update: %s", exc)
            return
        current = (check[0].get("state") if check else "") or ""
        if current == state:
            self.logger.info("change %s state confirmed -> %s", change_number, current)
        else:
            self.logger.warning(
                "change %s state is %s (requested %s). change_request.state is workflow-controlled "
                "on ServiceNow; the journal comment above is the authoritative write-back.",
                change_number,
                current,
                state,
            )


register_jobs(CreateSnowChange, UpdateSnowChange)
