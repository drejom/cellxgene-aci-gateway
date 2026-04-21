job "cellxgene-gateway" {
  datacenters = ["omhq"]
  type        = "service"

  constraint {
    attribute = "${meta.role}"
    value     = "lab"
  }

  group "gateway" {
    count = 1

    network {
      mode = "host"
      port "http" {
        static = 5005
      }
    }

    ephemeral_disk {
      size_mb = 300
    }

    service {
      name = "cellxgene-gateway"
      port = "http"
      tags = [
        "traefik.enable=true",
        "traefik.http.routers.cellxgene.rule=Host(`${EXTERNAL_HOST}`)",
        "traefik.http.routers.cellxgene.tls=true",
        "traefik.http.routers.cellxgene.tls.certresolver=cloudflare",
        "traefik.http.services.cellxgene.loadbalancer.server.port=5005",
      ]
      check {
        type     = "http"
        path     = "/api/status"
        interval = "30s"
        timeout  = "5s"
      }
    }

    task "cellxgene-gateway" {
      driver = "docker"

      config {
        image        = "ghcr.io/drejom/cellxgene-aci-gateway:latest"
        network_mode = "host"
      }

      env {
        # ── Gateway ──────────────────────────────────────────────────────────
        GATEWAY_PORT            = "5005"
        GATEWAY_EXPIRE_SECONDS  = "1800"
        GATEWAY_LOG_DIR         = "/logs"
        GATEWAY_LOG_LEVEL       = "INFO"
        CELLXGENE_BACKEND       = "aci"
        CELLXGENE_LOCATION      = "/usr/local/bin/cellxgene"
        CELLXGENE_DATA          = "/data"
        EXTERNAL_PROTOCOL       = "https"
        EXTERNAL_HOST           = "${EXTERNAL_HOST}"
        PROXY_FIX_FOR           = "1"
        PROXY_FIX_PROTO         = "1"
        PROXY_FIX_HOST          = "1"

        # ── Azure ─────────────────────────────────────────────────────────────
        AZURE_SUBSCRIPTION_ID   = "${AZURE_SUBSCRIPTION_ID}"
        AZURE_RESOURCE_GROUP    = "${AZURE_RESOURCE_GROUP}"
        AZURE_SUBNET_ID         = "${AZURE_SUBNET_ID}"

        # ── ACI provisioning ─────────────────────────────────────────────────
        ACI_CELLXGENE_IMAGE     = "${ACI_CELLXGENE_IMAGE}"
        ACI_REGISTRY_SERVER     = "${ACI_REGISTRY_SERVER}"
        ACI_REGISTRY_USER       = "${ACI_REGISTRY_USER}"
        ACI_REGISTRY_PASSWORD   = "${ACI_REGISTRY_PASSWORD}"
        ACI_MEMORY_GB           = "8"
        ACI_CPU                 = "4"
        # Per-dataset overrides (JSON):
        ACI_DATASET_RESOURCES   = "${ACI_DATASET_RESOURCES}"

        # ── Azure Files ───────────────────────────────────────────────────────
        ACI_FILES_ACCOUNT       = "${ACI_FILES_ACCOUNT}"
        ACI_FILES_SHARE         = "cellxgene-data"
        ACI_FILES_KEY           = "${ACI_FILES_KEY}"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
