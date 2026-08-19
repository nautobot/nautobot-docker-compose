"""Batfish digital-twin validation Job.

Builds a Batfish snapshot from the packaged FRR configs (optionally overlaid
with candidate configs for forward-twin change/upgrade validation) and checks
BGP session state plus reachability against the digital twin.
"""

import os
import re
import shutil
import tempfile

from nautobot.apps.jobs import JSONVar, Job, register_jobs

BATFISH_HOST = os.environ.get("BATFISH_HOST", "host.docker.internal")
BATFISH_PORT = int(os.environ.get("BATFISH_PORT", "9996"))
NETWORK = "lab"
SNAPSHOT_SRC = os.path.join(os.path.dirname(__file__), "batfish_snapshot")
ADDRESSING = {
    "core-rtr-01": "10.99.0.11",
    "edge-rtr-01": "10.99.0.12",
    "edge-rtr-02": "10.99.0.13",
}
REACHABILITY = [("edge-rtr-01", "2.2.2.2"), ("edge-rtr-02", "3.3.3.3")]


def _build_snapshot(candidates):
    snap_dir = tempfile.mkdtemp(prefix="twin_")
    cfg_dir = os.path.join(snap_dir, "configs", "configs")
    os.makedirs(cfg_dir, exist_ok=True)
    shutil.copytree(os.path.join(SNAPSHOT_SRC, "configs", "configs"), cfg_dir, dirs_exist_ok=True)
    for host, text in (candidates or {}).items():
        with open(os.path.join(cfg_dir, host + ".cfg"), "w", encoding="utf-8") as fh:
            fh.write(text)
    for host, ip in ADDRESSING.items():
        path = os.path.join(cfg_dir, host + ".cfg")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if ip not in text:
            text = re.sub(
                r"(interface eth0\n)(\s*no shutdown)",
                r"\1 ip address " + ip + r"/24\n\2",
                text,
            )
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
    return snap_dir


class ValidateBatfishTwin(Job):
    class Meta:
        name = "Validate Batfish Twin"
        description = "Validate BGP sessions and reachability against the Batfish digital twin (optionally with candidate configs for change/upgrade testing)"
        has_sensitive_variables = False

    candidates = JSONVar(
        description='Candidate configs as {"host": "config text"} to validate. Leave empty to validate the baseline twin.',
        required=False,
        default={},
    )

    def run(self, candidates=None):
        try:
            from pybatfish.client.session import Session
        except ImportError as exc:
            self.logger.error("pybatfish not installed in this image: %s", exc)
            return

        snap_dir = _build_snapshot(candidates)
        try:
            bf = Session(host=BATFISH_HOST, port_v2=BATFISH_PORT)
            bf.set_network(NETWORK)
            snap = bf.init_snapshot(snap_dir, name="candidate" if candidates else "live", overwrite=True)
            bf.set_snapshot(snap)
            self.logger.info("snapshot %s (mode=%s)", snap, "candidate" if candidates else "baseline")

            sessions = bf.q.bgpSessionStatus().answer().frame()
            established = 0
            for _, row in sessions.iterrows():
                status = row["Established_Status"]
                if status == "ESTABLISHED":
                    established += 1
                self.logger.info(
                    "bgp %s AS%s -> %s AS%s: %s",
                    row["Node"],
                    row["Local_AS"],
                    row["Remote_IP"],
                    row["Remote_AS"],
                    status,
                )

            reach_ok = True
            for peer, ip in REACHABILITY:
                try:
                    flows = bf.q.reachability(headers={"srcIps": "10.99.0.11", "dstIps": ip}).answer().frame()
                    ok = len(flows) > 0
                except Exception as exc:
                    ok = False
                    self.logger.error("reachability %s failed: %s", peer, exc)
                reach_ok = reach_ok and ok
                self.logger.info("reachability core-rtr-01 -> %s (%s): %s", peer, ip, "OK" if ok else "FAIL")

            total = len(sessions)
            all_ok = established == total and reach_ok
            self.logger.info(
                "twin summary: %d/%d bgp sessions established, reachability %s",
                established,
                total,
                "OK" if reach_ok else "FAIL",
            )
            self.logger.info("twin validation: %s", "PASS" if all_ok else "FAIL")
        finally:
            shutil.rmtree(snap_dir, ignore_errors=True)


register_jobs(ValidateBatfishTwin)