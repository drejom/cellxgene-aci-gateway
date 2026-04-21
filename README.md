# cellxgene-aci-gateway

A self-hosted [cellxgene](https://github.com/chanzuckerberg/cellxgene) gateway that provisions
**Azure Container Instances** on demand — one per dataset, torn down after inactivity.
Datasets live on an **Azure Files Premium** share, mounted read-only into each container.
Cold start ~30s (no file download).

Based on [cellxgene-gateway 0.4.2](https://github.com/Novartis/cellxgene-gateway) with the
subprocess backend replaced by ACI provisioning.

## Images

| Image | Purpose |
|---|---|
| `ghcr.io/drejom/cellxgene-aci-gateway:latest` | This gateway (Flask, runs on your VM) |
| `ghcr.io/drejom/cellxgene-aci-gateway/cellxgene:1.3.0` | cellxgene process (runs in ACI) |

## Quick start

```bash
cp deploy/.env.example deploy/.env
# edit deploy/.env — fill in Azure IDs, Files key, registry creds

docker compose -f deploy/docker-compose.yml up
```

Gateway listens on port 5005. Point a reverse proxy at it.

## Requirements

- Azure subscription with:
  - A VNet subnet delegated to ACI (`Microsoft.ContainerInstance/containerGroups`)
  - An Azure Files Premium share (≥100 GiB) with datasets uploaded
  - VM Managed Identity **or** Service Principal with `Contributor` on the resource group
- Docker (gateway) or Nomad (see `deploy/nomad.hcl`)

## Configuration

All config via environment variables. See [`deploy/.env.example`](deploy/.env.example) for the
full list with comments.

Key variables:

| Variable | Description |
|---|---|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription |
| `AZURE_RESOURCE_GROUP` | Resource group containing ACI + Files |
| `AZURE_SUBNET_ID` | Full resource ID of the ACI subnet |
| `ACI_CELLXGENE_IMAGE` | cellxgene container image |
| `ACI_FILES_ACCOUNT` | Storage account name |
| `ACI_FILES_KEY` | Storage account key |
| `ACI_DATASET_RESOURCES` | Per-dataset CPU/memory overrides (JSON) |
| `GATEWAY_EXPIRE_SECONDS` | Idle timeout before ACI teardown (default 3600) |

## Per-dataset resource overrides

```bash
ACI_DATASET_RESOURCES='{"pankbase":{"memory":56,"cpu":8,"flags":"--backed --max-category-items 500"}}'
```

Key is matched as substring of the filename (lowercase).

## Uploading datasets

```bash
export ACI_FILES_ACCOUNT=... ACI_FILES_KEY=... ACI_FILES_SHARE=cellxgene-data
./scripts/upload-dataset.sh /path/to/dataset.h5ad
```

## CI/CD

GitHub Actions builds and pushes both images to GHCR on push to `main`.
See [`.github/workflows/build-push.yml`](.github/workflows/build-push.yml).

No secrets needed beyond `GITHUB_TOKEN` (automatic).

## Docs

- [Architecture](docs/architecture.md)
- [h5ad compatibility](docs/h5ad-compatibility.md)
- [Cost model](docs/cost-model.md)

## License

Gateway code: Apache 2.0 (Novartis IBR, extended here).  
ACI backend (`aci_backend.py`, `backend_cache_patch.py`): MIT.
