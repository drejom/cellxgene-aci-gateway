"""
Monkey-patch BackendCache to swap in ACIBackend when
CELLXGENE_BACKEND=aci is set. Import this at container startup
via PYTHONSTARTUP or entrypoint before cellxgene-gateway runs.

Stage 2: CELLXGENE_BACKEND=subprocess (default, no change)
Stage 3: CELLXGENE_BACKEND=aci
"""
import os

backend_type = os.environ.get("CELLXGENE_BACKEND", "subprocess").lower()

# Patch index route via before_request so it survives the double-import from runpy
import os as _os
import cellxgene_gateway.gateway as _gw
from flask import render_template as _render_template, request as _request
from cellxgene_gateway.extra_scripts import get_extra_scripts as _get_extra_scripts

@_gw.app.before_request
def _intercept_index():
    if _request.path == "/" and _request.method == "GET":
        datasets = []
        for source in _gw.item_sources:
            try:
                tree = source.list_items(None)
                if tree and tree.items:
                    for item in tree.items:
                        datasets.append({"name": item.descriptor, "url": f"/view/{item.descriptor}/"})
            except Exception:
                pass
        if not datasets:
            data_dir = _os.environ.get("CELLXGENE_DATA", "")
            if data_dir and _os.path.isdir(data_dir):
                for fname in sorted(_os.listdir(data_dir)):
                    if fname.endswith(".h5ad"):
                        datasets.append({"name": fname, "url": f"/view/{fname}/"})
        return _render_template("index.html", datasets=datasets, extra_scripts=_get_extra_scripts())


if backend_type == "aci":
    from cellxgene_gateway import backend_cache
    from cellxgene_gateway.aci_backend import ACIBackend
    from cellxgene_gateway.cache_entry import CacheEntry

    _aci = ACIBackend()

    # Patch process_backend in backend_cache module
    backend_cache.process_backend = _aci

    # Patch CacheEntry.cellxgene_basepath to use ACI private IP
    _orig_basepath = CacheEntry.cellxgene_basepath

    def _aci_basepath(self):
        if hasattr(self, "_aci_base_url"):
            return self._aci_base_url
        return _orig_basepath(self)

    CacheEntry.cellxgene_basepath = _aci_basepath

    # Patch CacheEntry.terminate to delete ACI group
    _orig_terminate = CacheEntry.terminate

    def _aci_terminate(self):
        group_name = getattr(self, "_aci_group_name", None)
        if group_name:
            _aci.terminate(group_name)
        self.status = __import__(
            "cellxgene_gateway.cache_entry", fromlist=["CacheEntryStatus"]
        ).CacheEntryStatus.terminated

    CacheEntry.terminate = _aci_terminate

    # Patch serve_content to detect dead ACI containers and evict cache
    import requests as _requests
    from cellxgene_gateway.cache_entry import CacheEntryStatus as _CacheEntryStatus
    _orig_serve = CacheEntry.serve_content

    def _aci_serve_content(self, path):
        try:
            return _orig_serve(self, path)
        except (_requests.exceptions.ConnectionError,
                _requests.exceptions.ConnectTimeout,
                _requests.exceptions.Timeout) as e:
            # ACI container is gone or unreachable — evict cache so next request reprovisioned
            import logging
            logging.getLogger("cellxgene_gateway.aci_backend").warning(
                f"[ACI] proxy connection failed for {getattr(self, '_aci_group_name', '?')}, "
                f"evicting cache entry: {e}"
            )
            # Clear ACI state so next launch() call reprovisioned fresh
            self._aci_base_url = None
            self._aci_group_name = None
            self.status = _CacheEntryStatus.terminated
            # Return a clean 503 instead of a traceback 500
            from flask import make_response
            return make_response(
                "Dataset container is unavailable — please refresh to restart it.", 503
            )

    CacheEntry.serve_content = _aci_serve_content

    import logging
    logging.getLogger("cellxgene_gateway").info(
        "ACIBackend activated — containers will be provisioned in Azure"
    )
