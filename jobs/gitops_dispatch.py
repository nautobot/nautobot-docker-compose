"""GitOps workflow dispatch Job.

Triggers GitHub workflow_dispatch runs for the GitOps repositories so an
approved change flows into the CI/CD pipeline.

The GitHub token is read from /opt/nautobot/jobs/github.token. Repos must
have workflow_dispatch triggers on the target branch.

Repos and their workflow files:

    nautobot-ansible        ansible-ci.yml          (inputs: target, peer)
    nautobot-config-as-code config-as-code.yml
    nautobot-terraform      terraform-ci.yml
"""

import base64
import os

import requests

from nautobot.apps.jobs import Job, TextVar, register_jobs

TOKEN_PATH = "/opt/nautobot/jobs/github.token"
OWNER = "guptavishal2522-git"
WORKFLOWS = {
    "nautobot-config-as-code": "config-as-code.yml",
    "nautobot-ansible": "ansible-ci.yml",
    "nautobot-terraform": "terraform-ci.yml",
}


class DispatchGitOps(Job):
    class Meta:
        name = "Dispatch GitOps"
        description = "Trigger GitHub workflow_dispatch runs for approved changes"
        has_sensitive_variables = False

    change_number = TextVar(description="Change/approval number", required=False, default="")
    description = TextVar(description="Short description", required=False, default="")
    change_type = TextVar(
        description="Change type passed to the workflow (bgp-flap or config)",
        required=False,
        default="bgp-flap",
    )
    repos = TextVar(
        description="Comma-separated repos to dispatch (default nautobot-ansible)",
        required=False,
        default="nautobot-ansible",
    )
    target = TextVar(description="Ansible target device", required=False, default="core-rtr-01")
    peer = TextVar(description="Ansible BGP peer", required=False, default="10.99.0.12")
    candidate_config = TextVar(
        description="Full candidate config text to validate/apply (change_type=config)",
        required=False,
        default="",
    )
    expect = TextVar(
        description="JSON change-specific UAT expectations merged with base intent",
        required=False,
        default="",
    )
    use_case = TextVar(description="Natural-language use case for this change", required=False, default="")
    ai_fix = TextVar(description="Set 'true' when this run is an AI-proposed fix (re-approval)", required=False, default="")
    incident_id = TextVar(description="Agent incident id for completion callback", required=False, default="")

    def run(self, change_number="", description="", change_type="bgp-flap", repos="nautobot-ansible", target="core-rtr-01", peer="10.99.0.12", candidate_config="", expect="", use_case="", ai_fix="", incident_id=""):
        if not os.path.exists(TOKEN_PATH):
            self.logger.error("GitHub token file not found at %s", TOKEN_PATH)
            return
        with open(TOKEN_PATH, encoding="utf-8") as fh:
            token = fh.read().strip()
        if not token:
            self.logger.error("GitHub token file is empty")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        for repo in [x.strip() for x in repos.split(",") if x.strip()]:
            workflow = WORKFLOWS.get(repo)
            if not workflow:
                self.logger.error("unknown repo %s (expected: %s)", repo, ", ".join(WORKFLOWS))
                continue
            inputs = {}
            if repo == "nautobot-ansible":
                inputs = {
                    "target": target,
                    "peer": peer,
                    "change_number": change_number,
                    "change_type": change_type,
                }
                if incident_id:
                    inputs["incident_id"] = incident_id
                if candidate_config:
                    inputs["candidate_config_b64"] = base64.b64encode(candidate_config.encode("utf-8")).decode("ascii")
                if expect:
                    inputs["expect_b64"] = base64.b64encode(expect.encode("utf-8")).decode("ascii")
                if use_case:
                    inputs["use_case_b64"] = base64.b64encode(use_case.encode("utf-8")).decode("ascii")
                if ai_fix:
                    inputs["ai_fix"] = ai_fix
            url = f"https://api.github.com/repos/{OWNER}/{repo}/actions/workflows/{workflow}/dispatches"
            payload = {"ref": "main", "inputs": inputs}
            self.logger.info("dispatching %s workflow %s (inputs=%s)", repo, workflow, inputs or "none")
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
            except Exception as exc:
                self.logger.error("dispatch %s failed: %s", repo, exc)
                continue
            if resp.status_code == 204:
                self.logger.info(
                    "dispatched %s workflow %s (change=%s)",
                    repo,
                    workflow,
                    change_number or "n/a",
                )
            else:
                self.logger.error(
                    "dispatch %s rejected: %s %s",
                    repo,
                    resp.status_code,
                    resp.text[:200],
                )


register_jobs(DispatchGitOps)
