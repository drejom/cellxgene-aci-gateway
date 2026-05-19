"""
Gateway launcher — single clean import, no runpy double-import issue.
"""
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        })


def _setup_logging():
    log_dir = os.environ.get("GATEWAY_LOG_DIR", "")
    level = getattr(logging, os.environ.get("GATEWAY_LOG_LEVEL", "INFO"), logging.INFO)
    handlers = [logging.StreamHandler()]
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            os.path.join(log_dir, "gateway.jsonl"),
            when="midnight", backupCount=30, utc=True,
        )
        fh.setFormatter(_JsonFormatter())
        handlers.append(fh)
    logging.basicConfig(level=level, handlers=handlers,
                        format="%(asctime)s:%(name)s:%(levelname)s:%(message)s")


_setup_logging()

# 1. Import gateway — registers all routes
import cellxgene_gateway.gateway as gw
from cellxgene_gateway.extra_scripts import get_extra_scripts
from flask import render_template, request

# 2. Initialize data sources NOW (before any requests)
#    Also force the middleware's internal flag so it doesn't reinit on first request
gw.initialize_data_sources()
gw.data_sources_initialized = True  # prevents _init_on_first_wsgi_request from clearing sources

# 3. /api/status — dataset container states for pills UI
from flask import jsonify
from cellxgene_gateway.cache_entry import CacheEntryStatus
from cellxgene_gateway.backend_cache import BackendCache

def _check_aci_state(file_path):
    """Check live ACI container state for a dataset. Returns None if ACI backend not active."""
    try:
        from cellxgene_gateway import backend_cache
        be = backend_cache.process_backend
        if not hasattr(be, '_client'):
            return None
        group_name = be._container_group_name(file_path)
        cg = be._client.container_groups.get(
            os.environ.get("AZURE_RESOURCE_GROUP", "RG-KDL-CORE"), group_name)
        prov = cg.provisioning_state
        c_state = None
        if cg.containers and cg.containers[0].instance_view:
            c_state = cg.containers[0].instance_view.current_state.state
        if prov == "Succeeded" and c_state == "Running":
            return "loading"
        elif prov in ("Creating", "Pending"):
            return "provisioning"
        elif c_state == "Terminated" or prov in ("Failed", "Canceled"):
            return "error"
    except Exception:
        pass
    return None

@gw.app.route("/api/status")
def _api_status():
    """
    Returns JSON: { "datasets": { "<filename>": "idle|provisioning|loading|ready|error" } }
    Provisioning = CacheEntryStatus.loading + no _aci_base_url yet
    Loading      = CacheEntryStatus.loading + _aci_base_url set (ACI up, cellxgene reading)
    Ready        = CacheEntryStatus.loaded
    Error        = CacheEntryStatus.error (cross-checked with live ACI state)
    """
    result = {}
    for entry in gw.cache.entry_list:
        fname = os.path.basename(entry.key.file_path)
        if entry.status == CacheEntryStatus.loaded:
            result[fname] = "ready"
        elif entry.status == CacheEntryStatus.error:
            # Cross-check live ACI state — the cache error may be stale
            live = _check_aci_state(entry.key.file_path)
            result[fname] = live if live and live != "error" else "error"
        elif entry.status == CacheEntryStatus.loading:
            result[fname] = "loading" if getattr(entry, "_aci_base_url", None) else "provisioning"
        elif entry.status == CacheEntryStatus.terminated:
            result[fname] = "idle"
    return jsonify({"datasets": result})

# 4. Custom landing page — intercept GET / before the default index route
@gw.app.before_request
def _index_datasets():
    if request.path == "/" and request.method == "GET":
        datasets = []
        for source in gw.item_sources:
            try:
                tree = source.list_items(None)
                if tree and tree.items:
                    for item in tree.items:
                        datasets.append({
                            "name": item.descriptor,
                            "url": f"/view/{item.descriptor}/",
                        })
            except Exception:
                pass
        # Filesystem fallback — only if item_sources gave nothing
        if not datasets:
            data_dir = os.environ.get("CELLXGENE_DATA", "")
            if data_dir and os.path.isdir(data_dir):
                for fname in sorted(os.listdir(data_dir)):
                    if fname.endswith(".h5ad"):
                        datasets.append({"name": fname, "url": f"/view/{fname}/"})
        return render_template(
            "index.html",
            datasets=datasets,
            extra_scripts=get_extra_scripts(),
        )

# 4. ACI backend patch
if os.environ.get("CELLXGENE_BACKEND", "subprocess").lower() == "aci":
    import cellxgene_gateway.backend_cache_patch  # noqa: F401

# 5. Start server via gunicorn (multi-worker, not werkzeug dev server)
# werkzeug dev server serialises all requests — with 435k-cell datasets returning
# 3-10MB binary payloads, concurrent annotation/layout/gene fetches queue up and
# the browser fetch() times out, showing 'Unexpected HTTP error'.
# gunicorn with sync workers + threads handles concurrent requests correctly.
port = int(os.environ.get("GATEWAY_PORT", 5005))
workers = int(os.environ.get("GATEWAY_WORKERS", 2))
threads = int(os.environ.get("GATEWAY_THREADS", 4))
timeout = int(os.environ.get("GATEWAY_TIMEOUT", 120))

import gunicorn.app.base

class _StandaloneApp(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        for k, v in self.options.items():
            if k in self.cfg.settings:
                self.cfg.set(k.lower(), v)

    def load(self):
        return self.application

_StandaloneApp(gw.app, {
    "bind": f"0.0.0.0:{port}",
    "workers": workers,
    "threads": threads,
    "timeout": timeout,
    "worker_class": "sync",
    "accesslog": "-",
    "errorlog": "-",
    "loglevel": "info",
    "forwarded_allow_ips": "*",
    "proxy_protocol": False,
}).run()
