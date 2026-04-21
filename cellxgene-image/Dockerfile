FROM python:3.11-slim

# Minimal cellxgene image for running inside ACI.
# Built separately and pushed to your private registry.

RUN pip install --no-cache-dir cellxgene==1.3.0

# cellxgene listens on 0.0.0.0:5005 (port passed via CLI args in aci_backend.py)
EXPOSE 5005

# Not used directly — ACI backend passes the full cellxgene CLI command.
# This image just needs cellxgene on PATH.
ENTRYPOINT ["cellxgene"]
