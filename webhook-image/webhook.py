#!/usr/bin/env python3
"""
Nomad deploy webhook — validates X-Webhook-Secret, redeploys a named Nomad job.
Usage: python3 webhook.py
Env vars:
  WEBHOOK_SECRET   shared secret, must match X-Webhook-Secret header
  NOMAD_ADDR       Nomad API address (default http://127.0.0.1:4646)
  NOMAD_JOB        job name to redeploy (default cellxgene-gateway)
  PORT             listen port (default 9000)
"""
import os
import json
import subprocess
import hmac
import hashlib
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webhook")

SECRET = os.environ["WEBHOOK_SECRET"].encode()
NOMAD_ADDR = os.environ.get("NOMAD_ADDR", "http://127.0.0.1:4646")
NOMAD_JOB = os.environ.get("NOMAD_JOB", "cellxgene-gateway")
PORT = int(os.environ.get("PORT", "9000"))


def redeploy(cellxgene_image=None):
    """Inspect the live Nomad job spec, optionally update ACI_CELLXGENE_IMAGE, redeploy.

    cellxgene_image: if provided, overrides ACI_CELLXGENE_IMAGE in the job env.
      This is how CI pins the exact sha- tag built in the same workflow run,
      avoiding the stale-tag problem where 'cellxgene:1.3.0' or ':latest' might
      point to an old image already cached on the ACI host.
    """
    # Inspect current job spec
    r = subprocess.run(
        ["nomad", "job", "inspect", NOMAD_JOB],
        capture_output=True, text=True, env={**os.environ, "NOMAD_ADDR": NOMAD_ADDR}
    )
    if r.returncode != 0:
        raise RuntimeError(f"nomad job inspect failed: {r.stderr}")
    job = json.loads(r.stdout)

    # Optionally pin the cellxgene ACI image to the sha built in this CI run
    if cellxgene_image:
        env = job["Job"]["TaskGroups"][0]["Tasks"][0]["Env"]
        old = env.get("ACI_CELLXGENE_IMAGE", "(unset)")
        env["ACI_CELLXGENE_IMAGE"] = cellxgene_image
        log.info("ACI_CELLXGENE_IMAGE: %s -> %s", old, cellxgene_image)

    # Clear scheduling indexes so Nomad treats this as a new deployment
    for k in ["Version", "JobModifyIndex", "ModifyIndex", "CreateIndex"]:
        job["Job"][k] = 0
    job["Job"]["SubmitTime"] = None
    job["Job"]["Stop"] = False

    # Run it
    r = subprocess.run(
        ["nomad", "job", "run", "-json", "-"],
        input=json.dumps(job), capture_output=True, text=True,
        env={**os.environ, "NOMAD_ADDR": NOMAD_ADDR}
    )
    if r.returncode != 0:
        raise RuntimeError(f"nomad job run failed: {r.stderr}")
    return r.stdout.strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt % args)

    def do_POST(self):
        if self.path != "/deploy":
            self.send_response(404)
            self.end_headers()
            return

        # Validate secret
        incoming = self.headers.get("X-Webhook-Secret", "").encode()
        if not hmac.compare_digest(incoming, SECRET):
            log.warning("Rejected request — bad secret from %s", self.client_address)
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden\n")
            return

        # Read optional JSON body (e.g. {"cellxgene_image": "ghcr.io/.../cellxgene:sha-abc1234"})
        cellxgene_image = None
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try:
                body = json.loads(self.rfile.read(length))
                cellxgene_image = body.get("cellxgene_image")
            except Exception:
                pass

        # Respond immediately, run deploy in background (avoids proxy timeout on long nomad output)
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b"Accepted\n")

        def _run():
            log.info("Deploying %s (cellxgene_image=%s)...", NOMAD_JOB, cellxgene_image)
            try:
                out = redeploy(cellxgene_image=cellxgene_image)
                log.info("Deploy OK: %s", out[:200])
            except Exception as e:
                log.error("Deploy failed: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    log.info("Webhook listening on :%d for job %s", PORT, NOMAD_JOB)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
