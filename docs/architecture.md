# Architecture

## Overview

```
User browser
    │
    ▼
Traefik (reverse proxy)
    │  routes cellxgene.omeally.com → gateway:5005
    ▼
cellxgene-aci-gateway  (this repo, runs as Nomad job on lab VM)
    │  on first /view/<dataset>/ request:
    │    1. BackendCache miss → ACIBackend.launch()
    │    2. Create ACI container group (Azure Container Instances)
    │    3. Mount Azure Files share at /data (read-only)
    │    4. Poll until container Running + has private IP
    │    5. Poll cellxgene HTTP until ready
    │    6. Proxy all subsequent requests to ACI private IP
    │
    │  on GATEWAY_EXPIRE_SECONDS inactivity:
    │    7. ACIBackend.terminate() → delete container group
    │
    ▼
Azure Container Instance  (per dataset, ephemeral)
    │  image: ghcr.io/drejom/cellxgene-aci-gateway/cellxgene:1.3.0
    │  subnet: VNET-KDL-CORE/aci (private, not internet-exposed)
    │  cmd: cellxgene launch --host 0.0.0.0 --port 5005 /data/<dataset>.h5ad
    ▼
Azure Files Premium share  (persistent, all datasets)
    account: kdlcellxgene
    share:   cellxgene-data
    mount:   /data (read-only in ACI)
```

## Cold start times

| Phase | Typical |
|---|---|
| ACI provisioning (Succeeded state) | ~30s |
| cellxgene loading small dataset (<5GB) | ~2–3 min |
| cellxgene loading large dataset (25GB) | ~10–15 min |

## Dataset resources

Default: 8 GB RAM / 2 vCPU. Override per-dataset via `ACI_DATASET_RESOURCES`:

```json
{"pankbase": {"memory": 56, "cpu": 8, "flags": "--backed --max-category-items 500"}}
```

Key is matched as a substring of the filename (lowercase).

## Network

- Gateway lives on lab VM (172.16.100.20) with Nomad
- ACI containers get private IPs in 10.2.1.0/24 (aci subnet)
- Gateway reaches ACI via private IP — no public exposure needed
- Azure Files mounted via SMB over private endpoint (service endpoint on aci subnet)

## Authentication

- Gateway → Azure APIs: VM Managed Identity (no credentials needed on lab VM)
- ACI → private registry: `ACI_REGISTRY_*` env vars
- ACI → Azure Files: storage account key (`ACI_FILES_KEY`)
