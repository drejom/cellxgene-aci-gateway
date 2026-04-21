# Cost Model (westus2, Apr 2026)

## Azure Files Premium

| Item | Value |
|---|---|
| Share size | 100 GiB minimum |
| Rate | ~$0.12/GiB/month |
| Monthly cost | ~$12.50/month (fixed at 100 GiB) |

## Azure Container Instances

ACI billed per second of container runtime (provisioned → deleted).

| Config | vCPU rate | Memory rate | Example |
|---|---|---|---|
| Standard | $0.0000125/vCPU-s | $0.0000013/GB-s | — |
| 2 vCPU / 8 GB, 4h | — | — | ~$0.42 |
| 8 vCPU / 56 GB, 4h | — | — | ~$2.69 |

Containers are deleted after `GATEWAY_EXPIRE_SECONDS` of inactivity (default 1800s).
Cost is zero when no containers are running.

## Notes

- Azure Files minimum quota is 100 GiB for Premium FileStorage (not 32 GiB)
- Storage account `default-action` must stay `Allow` — service endpoints don't
  restrict SMB mounts from within ACI on the same VNet
- Security boundary = storage account key (stored in Vault)
