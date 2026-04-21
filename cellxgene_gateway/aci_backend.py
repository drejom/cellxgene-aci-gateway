"""
ACI Backend for cellxgene-gateway (Stage 3)

Replaces SubprocessBackend with Azure Container Instance provisioning.
Each dataset gets its own ACI container group, spun up on demand and torn
down after GATEWAY_EXPIRE_SECONDS of inactivity.

Authentication: VM Managed Identity (no credentials required).
Network: ACI containers join the lab VNET subnet, gateway reaches them
         via private IP on port 5005.

Required env vars:
  AZURE_SUBSCRIPTION_ID   - Azure subscription
  AZURE_RESOURCE_GROUP    - Resource group (e.g. RG-KDL-CORE)
  AZURE_SUBNET_ID         - Full subnet resource ID for ACI VNET injection
  ACI_MEMORY_GB           - Memory per container in GB (default: 16)
  ACI_CPU                 - CPU cores per container (default: 4)
  ACI_CELLXGENE_IMAGE     - Container image (default: kdlcoreacr.azurecr.io/cellxgene:1.3.0)
  ACI_REGISTRY_SERVER     - Registry login server (optional, for private registries)
  ACI_REGISTRY_USER       - Registry username (optional)
  ACI_REGISTRY_PASSWORD   - Registry password (optional)
  ACI_FILES_ACCOUNT       - Azure Files storage account name (e.g. kdlcellxgene)
  ACI_FILES_SHARE         - Azure Files share name (default: cellxgene-data)
  ACI_FILES_KEY           - Azure Files storage account key

Storage model: Azure Files Premium share mounted at /data in each ACI container.
No download at startup — files are already on the share. Cold start ~30s vs ~20min.
HPC pipeline uploads directly to the share; changes visible on next container launch.
"""

import json
import logging
import logging.handlers
import os
import time
import uuid
from datetime import datetime, timezone


def _timing_logger():
    """Returns a logger that writes JSON timing records to /logs/aci_timing.jsonl."""
    log_dir = os.environ.get("GATEWAY_LOG_DIR", "")
    tl = logging.getLogger("aci.timing")
    if log_dir and not tl.handlers:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, "aci_timing.jsonl"),
            when="midnight", backupCount=90, utc=True,
        )
        fh.setFormatter(logging.Formatter("%(message)s"))
        tl.addHandler(fh)
        tl.propagate = False
    return tl


def _log_timing(event: str, dataset: str, elapsed_s: float = None, **extra):
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        "dataset": dataset,
    }
    if elapsed_s is not None:
        record["elapsed_s"] = round(elapsed_s, 1)
    record.update(extra)
    _timing_logger().info(json.dumps(record))

from azure.identity import ManagedIdentityCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    Container,
    ContainerGroup,
    ContainerPort,
    EnvironmentVariable,
    ImageRegistryCredential,
    OperatingSystemTypes,
    ResourceRequests,
    ResourceRequirements,
    ContainerGroupSubnetId,
)

from cellxgene_gateway.cache_entry import CacheEntryStatus
from cellxgene_gateway.process_exception import ProcessException

logger = logging.getLogger(__name__)

# Config from env
SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID")
RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "RG-KDL-CORE")
SUBNET_ID = os.environ.get("AZURE_SUBNET_ID")
ACI_MEMORY_GB = float(os.environ.get("ACI_MEMORY_GB", "8"))
ACI_CPU = float(os.environ.get("ACI_CPU", "2"))

# Per-dataset overrides — JSON env var, e.g.:
# ACI_DATASET_RESOURCES='{"pankbase":{"memory":56,"cpu":8}}'
# Key matched as substring of filename (lowercase)
import json as _json
_DATASET_RESOURCES = _json.loads(os.environ.get("ACI_DATASET_RESOURCES", "{}"))

def _dataset_resources(filename: str):
    """Return (memory_gb, cpu, extra_flags) for a given filename."""
    name_lower = filename.lower()
    for key, vals in _DATASET_RESOURCES.items():
        if key.lower() in name_lower:
            return (
                float(vals.get("memory", ACI_MEMORY_GB)),
                float(vals.get("cpu", ACI_CPU)),
                vals.get("flags", ""),
            )
    return ACI_MEMORY_GB, ACI_CPU, ""
ACI_IMAGE = os.environ.get("ACI_CELLXGENE_IMAGE", "kdlcoreacr.azurecr.io/cellxgene:1.3.0")
ACI_REGISTRY_SERVER = os.environ.get("ACI_REGISTRY_SERVER", "kdlcoreacr.azurecr.io")
ACI_REGISTRY_USER = os.environ.get("ACI_REGISTRY_USER")
ACI_REGISTRY_PASSWORD = os.environ.get("ACI_REGISTRY_PASSWORD")
ACI_FILES_ACCOUNT = os.environ.get("ACI_FILES_ACCOUNT", "kdlcellxgene")
ACI_FILES_SHARE  = os.environ.get("ACI_FILES_SHARE", "cellxgene-data")
ACI_FILES_KEY    = os.environ.get("ACI_FILES_KEY")
CELLXGENE_PORT = 5005
POLL_INTERVAL = 5   # seconds between ACI state polls
POLL_TIMEOUT = 600  # seconds before giving up on provisioning (10 min for large images)


class ACIBackend:
    """
    Drop-in replacement for SubprocessBackend.
    Implements the same launch() interface but provisions ACI instead of
    a local subprocess.
    """

    def __init__(self):
        self._credential = ManagedIdentityCredential()
        self._client = ContainerInstanceManagementClient(
            self._credential, SUBSCRIPTION_ID
        )

    def _container_group_name(self, file_path: str) -> str:
        """Stable, Azure-safe name derived from the dataset filename."""
        stem = os.path.splitext(os.path.basename(file_path))[0]
        # ACI names: lowercase alphanumeric + hyphens, max 63 chars
        safe = "".join(c if c.isalnum() else "-" for c in stem.lower())[:50]
        return f"cellxgene-{safe}"

    def launch(self, cellxgene_loc, scripts, cache_entry):
        """
        Provision an ACI container for cache_entry.key.file_path.
        Blocks until the container is Running and updates cache_entry
        with the private IP so the gateway can proxy to it.
        """
        file_path = cache_entry.key.file_path
        # file_path inside container is /data/<filename>
        h5ad_filename = os.path.basename(file_path)
        container_path = f"/data/{h5ad_filename}"
        group_name = self._container_group_name(file_path)
        mem_gb, cpu, extra_flags = _dataset_resources(h5ad_filename)

        logger.info(f"[ACI] Provisioning {group_name} for {h5ad_filename} ({mem_gb}GB RAM, {cpu} vCPU)")
        t_start = time.monotonic()
        _log_timing("launch_requested", h5ad_filename, memory_gb=mem_gb, cpu=cpu)

        # Check if container already exists and is running — skip provisioning
        try:
            existing = self._client.container_groups.get(RESOURCE_GROUP, group_name)
            ex_state = existing.provisioning_state
            ex_ip = existing.ip_address
            container_state = existing.containers[0].instance_view.current_state.state if existing.containers else None
            logger.info(f"[ACI] {group_name} already exists: provState={ex_state} containerState={container_state}")
            if ex_state == "Succeeded" and ex_ip and container_state == "Running":
                # Container is running — go straight to HTTP readiness poll
                private_ip = ex_ip.ip
                cellxgene_url = f"http://{private_ip}:{CELLXGENE_PORT}"
                import urllib.request
                ready_elapsed = 0
                ready_timeout = 900
                cache_entry.append_output(f"Container already running, waiting for cellxgene...\n")
                _log_timing("container_reused", h5ad_filename, elapsed_s=time.monotonic()-t_start)
                while ready_elapsed < ready_timeout:
                    try:
                        urllib.request.urlopen(cellxgene_url, timeout=5)
                        logger.info(f"[ACI] {group_name} ready at {cellxgene_url}")
                        _log_timing("cellxgene_ready", h5ad_filename, elapsed_s=time.monotonic()-t_start, reused=True)
                        break
                    except Exception:
                        time.sleep(10)
                        ready_elapsed += 10
                        cache_entry.append_output(f"Waiting for cellxgene... ({ready_elapsed}s)\n")
                cache_entry._aci_group_name = group_name
                cache_entry._aci_base_url = cellxgene_url
                cache_entry.set_loaded(group_name)
                return
            elif ex_state in ("Failed", "Canceled") or container_state == "Terminated":
                # Dead container — delete and reprovision
                logger.info(f"[ACI] {group_name} in bad state, deleting and reprovisioning")
                _log_timing("container_deleted", h5ad_filename, elapsed_s=time.monotonic()-t_start, reason=ex_state)
                self._client.container_groups.begin_delete(RESOURCE_GROUP, group_name).result()
        except Exception as e:
            if "ResourceNotFound" not in str(e) and "NotFound" not in str(e):
                logger.warning(f"[ACI] pre-check error (continuing): {e}")

        # Azure Files volume mounted at /data — file already present, no download needed
        startup_script = (
            f"cellxgene launch --host 0.0.0.0 --port {CELLXGENE_PORT} "
            f"--disable-diffexp --disable-annotations "
            f"--title '{os.path.splitext(h5ad_filename)[0]}' "
            f"{extra_flags} "
            f"/data/{h5ad_filename}"
        )

        from azure.mgmt.containerinstance.models import (
            Volume, AzureFileVolume, VolumeMount
        )

        volume = Volume(
            name="cellxgene-data",
            azure_file=AzureFileVolume(
                share_name=ACI_FILES_SHARE,
                storage_account_name=ACI_FILES_ACCOUNT,
                storage_account_key=ACI_FILES_KEY,
                read_only=True,
            )
        )

        container = Container(
            name="cellxgene",
            image=ACI_IMAGE,
            command=["/bin/bash", "-c", startup_script],
            resources=ResourceRequirements(
                requests=ResourceRequests(
                    memory_in_gb=mem_gb,
                    cpu=cpu,
                )
            ),
            ports=[ContainerPort(port=CELLXGENE_PORT, protocol="TCP")],
            volume_mounts=[VolumeMount(name="cellxgene-data", mount_path="/data", read_only=True)],
            environment_variables=[],
        )

        registry_creds = None
        if ACI_REGISTRY_USER and ACI_REGISTRY_PASSWORD:
            registry_creds = [ImageRegistryCredential(
                server=ACI_REGISTRY_SERVER,
                username=ACI_REGISTRY_USER,
                password=ACI_REGISTRY_PASSWORD,
            )]

        group = ContainerGroup(
            location="westus2",
            containers=[container],
            os_type=OperatingSystemTypes.linux,
            restart_policy="Never",
            subnet_ids=[ContainerGroupSubnetId(id=SUBNET_ID)] if SUBNET_ID else None,
            image_registry_credentials=registry_creds,
            volumes=[volume],
        )

        _log_timing("aci_create_start", h5ad_filename, elapsed_s=time.monotonic()-t_start)
        try:
            poller = self._client.container_groups.begin_create_or_update(
                RESOURCE_GROUP, group_name, group
            )
        except Exception as e:
            msg = f"ACI create failed: {e}"
            logger.error(f"[ACI] {msg}")
            _log_timing("aci_create_failed", h5ad_filename, elapsed_s=time.monotonic()-t_start, error=str(e))
            cache_entry.status = CacheEntryStatus.error
            cache_entry.set_error(msg, str(e), 500)
            raise ProcessException.from_cache_entry(cache_entry)

        # Poll until Running
        elapsed = 0
        private_ip = None
        while elapsed < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            try:
                cg = self._client.container_groups.get(RESOURCE_GROUP, group_name)
                state = cg.provisioning_state
                ip_obj = cg.ip_address
                logger.info(f"[ACI] {group_name} state={state} elapsed={elapsed}s")
                cache_entry.append_output(f"Provisioning... ({state}, {elapsed}s)\n")

                if state == "Succeeded" and ip_obj:
                    private_ip = ip_obj.ip
                    _log_timing("aci_provisioned", h5ad_filename, elapsed_s=time.monotonic()-t_start)
                    # Set _aci_base_url now so /api/status can show "loading" vs "provisioning"
                    cache_entry._aci_base_url = f"http://{private_ip}:{CELLXGENE_PORT}"
                    break
                elif state in ("Failed", "Canceled"):
                    msg = f"ACI provisioning {state}"
                    _log_timing("aci_provision_failed", h5ad_filename, elapsed_s=time.monotonic()-t_start, state=state)
                    cache_entry.status = CacheEntryStatus.error
                    cache_entry.set_error(msg, state, 500)
                    raise ProcessException.from_cache_entry(cache_entry)
            except ProcessException:
                raise
            except Exception as e:
                logger.warning(f"[ACI] poll error: {e}")

        if not private_ip:
            msg = f"ACI timed out after {POLL_TIMEOUT}s"
            _log_timing("aci_timeout", h5ad_filename, elapsed_s=time.monotonic()-t_start)
            cache_entry.status = CacheEntryStatus.error
            cache_entry.set_error(msg, "", 504)
            raise ProcessException.from_cache_entry(cache_entry)

        # Wait for cellxgene to finish loading (poll HTTP)
        # Large datasets (>10GB) can take 10+ minutes to load into memory
        cellxgene_url = f"http://{private_ip}:{CELLXGENE_PORT}"
        import urllib.request
        ready_elapsed = 0
        ready_timeout = 900  # 15 min — enough for 25GB dataset
        while ready_elapsed < ready_timeout:
            try:
                urllib.request.urlopen(cellxgene_url, timeout=5)
                logger.info(f"[ACI] {group_name} ready at {cellxgene_url}")
                _log_timing("cellxgene_ready", h5ad_filename, elapsed_s=time.monotonic()-t_start, reused=False)
                break
            except Exception:
                time.sleep(10)
                ready_elapsed += 10
                cache_entry.append_output(f"Waiting for cellxgene... ({ready_elapsed}s)\n")

        # Store private IP in pid field (gateway uses cellxgene_basepath())
        # We patch cache_entry to return ACI IP instead of localhost
        cache_entry._aci_group_name = group_name
        cache_entry._aci_base_url = cellxgene_url
        cache_entry.set_loaded(group_name)  # pid = group_name for logging


    def terminate(self, group_name: str):
        """Delete the ACI container group."""
        if not group_name or not group_name.startswith("cellxgene-"):
            return
        try:
            logger.info(f"[ACI] Deleting container group {group_name}")
            self._client.container_groups.begin_delete(RESOURCE_GROUP, group_name)
        except Exception as e:
            logger.warning(f"[ACI] Delete failed for {group_name}: {e}")
