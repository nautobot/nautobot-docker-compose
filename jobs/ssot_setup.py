"""Bootstrap Job: create/update SSoT integration objects from integrations.json."""

import json
import os

from nautobot.apps.jobs import Job, register_jobs
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration
from nautobot.extras.models.secrets import Secret, SecretsGroup, SecretsGroupAssociation

CONFIG_PATH = "/opt/nautobot/jobs/integrations.json"

ACCESS_TYPE = SecretsGroupAccessTypeChoices.TYPE_REST

SECRET_TYPES = {
    "Username": SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    "Password": SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
}


class SSOTSetup(Job):
    class Meta:
        name = "SSOT Integration Setup"
        description = (
            "Create or update SSoT integration objects (SecretsGroups, Secrets, ExternalIntegrations) "
            "from integrations.json. Re-run after editing that file to add/change endpoints or credentials."
        )
        has_sensitive_variables = False

    def run(self):
        if not os.path.exists(CONFIG_PATH):
            self.logger.error("integrations.json not found at %s", CONFIG_PATH)
            return
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        for name, cfg in data.get("integrations", {}).items():
            self._setup_integration(name, cfg)

    def _setup_integration(self, name, cfg):
        secrets_group = self._ensure_secrets_group(name, cfg.get("secrets", []))
        ext, created = ExternalIntegration.objects.update_or_create(
            name=cfg.get("integration_name", name),
            defaults={
                "remote_url": cfg.get("url", ""),
                "http_method": cfg.get("http_method", "POST"),
                "verify_ssl": cfg.get("verify_ssl", False),
                "secrets_group": secrets_group,
            },
        )
        action = "created" if created else "updated"
        self.logger.info(
            "%s ExternalIntegration %s (url=%s)",
            action,
            ext.name,
            ext.remote_url or "<none>",
        )
        self._wire_servicenow_config(name, cfg, secrets_group)

    def _ensure_secrets_group(self, name, secrets):
        secrets_group, _ = SecretsGroup.objects.get_or_create(name=f"{name} Secrets")
        for secret_def in secrets:
            secret_type_name = secret_def.get("secret_type", "")
            env_var = secret_def.get("env_var", "")
            if secret_type_name not in SECRET_TYPES or not env_var:
                self.logger.warning("skipping malformed secret definition: %s", secret_def)
                continue
            secret, _ = Secret.objects.update_or_create(
                name=secret_def.get("name", env_var),
                defaults={"provider": "environment-variable", "parameters": {"variable": env_var}},
            )
            secret_type = SECRET_TYPES[secret_type_name]
            existing = SecretsGroupAssociation.objects.filter(
                secrets_group=secrets_group,
                access_type=ACCESS_TYPE,
                secret_type=secret_type,
            ).first()
            if existing:
                existing.secret = secret
                existing.save()
            else:
                SecretsGroupAssociation.objects.create(
                    secrets_group=secrets_group,
                    secret=secret,
                    access_type=ACCESS_TYPE,
                    secret_type=secret_type,
                )
            self.logger.info(
                "secret %s (%s) -> %s",
                secret.name,
                secret_type_name,
                ACCESS_TYPE,
            )
        return secrets_group

    def _wire_servicenow_config(self, name, cfg, secrets_group):
        if name.lower() != "servicenow":
            return
        try:
            from nautobot_ssot.integrations.servicenow.models import SSOTServiceNowConfig
        except ImportError:
            return
        config = SSOTServiceNowConfig.load()
        config.servicenow_instance = cfg.get("url", "").rstrip("/")
        config.servicenow_secrets = secrets_group
        config.validated_save()
        self.logger.info(
            "ServiceNow SSoT config updated (instance=%s)",
            config.servicenow_instance,
        )


register_jobs(SSOTSetup)