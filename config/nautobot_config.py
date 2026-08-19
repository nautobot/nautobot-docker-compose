"""Nautobot development configuration file."""

# pylint: disable=invalid-envvar-default
import os
import sys

from celery.schedules import crontab
from nautobot.core.settings import *  # noqa: F403  # pylint: disable=wildcard-import,unused-wildcard-import
from nautobot.core.settings_funcs import is_truthy, parse_redis_connection

#
# Debug
#

DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", False))

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

#
# Logging
#

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

#
# Redis
#

# Redis Cacheops
CACHEOPS_REDIS = parse_redis_connection(redis_database=1)

#
# Celery settings are not defined here because they can be overloaded with
# environment variables. By default they use `CACHES["default"]["LOCATION"]`.
#

# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = [
    "nautobot_golden_config",
    "nautobot_ssot",
    "nautobot_device_onboarding",
    "nautobot_firewall_models",
    "nautobot_device_lifecycle_mgmt",
    "nautobot_chatops",
    "nautobot_circuit_maintenance",
    "nautobot_design_builder",
    "nautobot_floor_plan",
    "welcome_wizard",
    "nautobot_bgp_models",
    "nautobot_capacity_metrics",
    "nautobot_secrets_providers",
    "nautobot_dns_models",
]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    "nautobot_example_plugin": {},
}

# Daily 02:00 UTC backup of live configs to the golden-source repo.
# This uses the agent's /admin/backup endpoint via the Backup Configurations job.
CELERY_BEAT_SCHEDULE = {
    "daily-golden-config-backup": {
        "task": "nautobot.extras.jobs.run_job",
        "schedule": crontab(minute=0, hour=2),
        "kwargs": {
            "job_class_path": "trigger_agent_backup.TriggerAgentBackup",
            "data": {"targets": []},
            "commit": True,
        },
    },
}
