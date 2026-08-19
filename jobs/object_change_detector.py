"""Nautobot ObjectChange detector Job.

Scans recent ObjectChanges and enqueues a pending approval in the
incident-agent approval queue so a human can review and approve any
Nautobot-originated change before it propagates to CI/CD.

The detector keeps a marker (last processed ObjectChange time) in Redis so
each change is surfaced only once. Run it on a schedule (Celery beat) or
on demand.

The agent API base URL comes from NAUTOBOT_AGENT_URL
(default http://incident-agent:8000).
"""

import json
import os

import redis
import requests
from django.utils import timezone

from nautobot.apps.jobs import Job, register_jobs
from nautobot.extras.models import ObjectChange

AGENT_URL = os.getenv("NAUTOBOT_AGENT_URL", "http://incident-agent:8000").rstrip("/")
REDIS_URL = os.getenv("NAUTOBOT_CACHEOPS_REDIS", "redis://redis:6379/1")
MARKER_KEY = "detector:last_objectchange_time"
MAX_SAMPLE = 20

NOISE_TYPES = {"job", "jobresult", "joblogentry", "objectchange", "scheduledjob"}


class DetectNautobotChanges(Job):
    class Meta:
        name = "Detect Nautobot Changes"
        description = "Scan recent ObjectChanges and enqueue a pending approval for human decision"
        has_sensitive_variables = False

    def run(self):
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        last = r.get(MARKER_KEY)
        now = timezone.now()

        qs = ObjectChange.objects.exclude(changed_object_type__model__in=NOISE_TYPES)
        if last:
            qs = qs.filter(time__gt=last)
        else:
            qs = qs.none()

        count = qs.count()
        if count == 0:
            r.set(MARKER_KEY, now.isoformat())
            self.logger.info("no new object changes since last run")
            return

        sample = list(qs.order_by("-time")[:MAX_SAMPLE])
        lines = [
            "%s %s %s %s" % (
                c.time.strftime("%H:%M:%S"),
                c.action,
                c.changed_object_type.model,
                c.object_repr,
            )
            for c in sample
        ]
        description = "%d Nautobot object change(s) detected:\n%s" % (
            count,
            "\n".join(lines),
        )
        action = {
            "type": "nautobot_change",
            "count": count,
            "changes": [
                {
                    "id": str(c.id),
                    "action": c.action,
                    "object_type": c.changed_object_type.model,
                    "object_repr": c.object_repr,
                }
                for c in sample
            ],
        }

        try:
            resp = requests.post(
                f"{AGENT_URL}/approvals",
                json={"description": description, "incident_id": "", "action": action},
                timeout=30,
            )
            resp.raise_for_status()
            approval_id = resp.json()["id"]
        except Exception as exc:
            self.logger.error("failed to enqueue change approval: %s", exc)
            return

        r.set(MARKER_KEY, now.isoformat())
        self.logger.info(
            "enqueued approval %s for %d object change(s)",
            approval_id[:8],
            count,
        )
        for line in lines:
            self.logger.info("  %s", line)


register_jobs(DetectNautobotChanges)