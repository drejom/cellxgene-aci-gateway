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
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webhook")

SECRET = os.environ["WEBHOOK_SECRET"].encode()
NOMAD_ADDR = os.environ.get("NOMAD_ADDR", "http://127.0.0.1:4646")
NOMAD_JOB = os.environ.get("NOMAD_JOB", "cellxgene-gateway")
PORT = int(os.environ.get("PORT", "9000"))


def redeploy():
    # Inspect current job spec
    r = subprocess.run(
        ["nomad", "job", "inspect", NOMAD_JOB],
        capture_output=True, text=True, env={**os.environ, "NOMAD_ADDR": NOMAD_ADDR}
    )
    if r.returncode != 0:
        raise RuntimeError(f"nomad job inspect failed: {r.stderr}")
    job = json.loads(r.stdout)

    # Bump job version to force redeploy (clear stable version)
    job["Job"]["Version"] = None
    job["Job"]["JobModifyIndex"] = 0

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

        log.info("Deploying %s ...", NOMAD_JOB)
        try:
            out = redeploy()
            log.info("Deploy OK: %s", out[:200])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"OK\n{out}\n".encode())
        except Exception as e:
            log.error("Deploy failed: %s", e)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"ERROR: {e}\n".encode())

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
