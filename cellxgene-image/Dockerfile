FROM python:3.11-slim

# Minimal cellxgene image for running inside ACI.
# Built separately and pushed to your private registry.

# werkzeug>=3.0 and flask>=3.0 break cellxgene 1.3.0 (AssertionError: applications must write bytes)
# Pin to last known-good versions — see github.com/Novartis/cellxgene-gateway/issues/87
RUN pip install --no-cache-dir cellxgene==1.3.0 werkzeug==2.3.0 flask==2.2.2

# cellxgene listens on 0.0.0.0:5005 (port passed via CLI args in aci_backend.py)
EXPOSE 5005

# Not used directly — ACI backend passes the full cellxgene CLI command.
# This image just needs cellxgene on PATH.
ENTRYPOINT ["cellxgene"]
