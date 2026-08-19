"""Nautobot job: upload current golden-repo configs to Batfish as a new snapshot.

The snapshot is built from the repo's ``*-frr.conf`` files, normalised for
Batfish (eth0 addresses inserted, filenames as ``<hostname>.cfg``).
"""
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

from nautobot.apps.jobs import Job, StringVar, register_jobs

BATFISH_HOST = os.getenv("BATFISH_HOST", "host.docker.internal")
BATFISH_PORT = int(os.getenv("BATFISH_PORT", "9996"))
REPO_DIR = "/data/golden-repo"
NETWORK = os.getenv("TWIN_NETWORK", "lab")

ADDRESSING = {
    "core-rtr-01": "10.99.0.11",
    "edge-rtr-01": "10.99.0.12",
    "edge-rtr-02": "10.99.0.13",
}


def _ensure_eth0(text: str, host: str) -> str:
    ip = ADDRESSING.get(host)
    if not ip or f"{ip}/24" in text:
        return text
    block = re.search(r"(?m)^interface eth0\s*\n((?:\s+[^\n]*\n)*)", text)
    if block:
        if "ip address" not in block.group(0):
            text = text[: block.start(1)] + f" ip address {ip}/24\n" + text[block.start(1):]
    else:
        text += f"\ninterface eth0\n ip address {ip}/24\n no shutdown\n"
    return text


class SnapshotBatfish(Job):
    class Meta:
        name = "Snapshot Batfish"
        description = "Upload current golden-repo configs to Batfish as a new snapshot"
        has_sensitive_variables = False

    snapshot_name = StringVar(
        description="Snapshot name (default: timestamp)",
        required=False,
        default="",
    )

    def run(self, snapshot_name=""):
        from pybatfish.client.session import Session

        if not snapshot_name:
            snapshot_name = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")

        snap_dir = tempfile.mkdtemp(prefix="batfish_")
        cfg_dir = os.path.join(snap_dir, "configs", "configs")
        os.makedirs(cfg_dir, exist_ok=True)

        try:
            for filename in os.listdir(REPO_DIR):
                if not filename.endswith("-frr.conf"):
                    continue
                host = filename[: -len("-frr.conf")]
                with open(os.path.join(REPO_DIR, filename), encoding="utf-8") as fh:
                    text = fh.read()
                text = _ensure_eth0(text, host)
                with open(os.path.join(cfg_dir, f"{host}.cfg"), "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.logger.info("added %s to snapshot", host)

            bf = Session(host=BATFISH_HOST, port_v2=BATFISH_PORT)
            bf.set_network(NETWORK)
            snap = bf.init_snapshot(snap_dir, name=snapshot_name, overwrite=True)
            self.logger.info("Batfish snapshot created: %s", snap)
            return {"snapshot_name": snapshot_name, "snapshot_uuid": str(snap)}
        finally:
            shutil.rmtree(snap_dir, ignore_errors=True)


register_jobs(SnapshotBatfish)
