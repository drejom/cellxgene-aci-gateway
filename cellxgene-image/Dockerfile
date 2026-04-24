FROM python:3.11-slim

# Minimal cellxgene image for running inside ACI.
# Built separately and pushed to your private registry.

# Dependency notes:
#
# werkzeug pin history (DO NOT BLINDLY RE-PIN WITHOUT READING THIS):
#
# Problem 1: "AssertionError: applications must write bytes" on large dataset responses
#   Root cause: cellxgene 1.3.0 was returning non-bytes from obsm stored as pandas
#               DataFrames (SeuratDisk encoding bug). Fixed by h5py in-place conversion
#               of obsm groups to plain float32 arrays. NOT a werkzeug version issue.
#   The assertion exists in werkzeug 2.3.x AND 3.x — downgrading werkzeug does NOT fix it.
#   See: https://github.com/Novartis/cellxgene-gateway/issues/87
#
# Problem 2: "set_cookie() got an unexpected keyword argument 'partitioned'"
#   Root cause: werkzeug 2.3.x missing 'partitioned' kwarg added in werkzeug 3.0.3 (May 2024)
#   Flask 3.x calls set_cookie(partitioned=...) — requires werkzeug >=3.0.3
#   DO NOT pin werkzeug below 3.0.3 with Flask 3.x.
#
# Conclusion: let pip resolve werkzeug naturally (will be 3.x, compatible with Flask 3.x).
#
# Problem 3: "AssertionError: applications must write bytes" on ALL binary endpoints
#   (layout/obs, annotations/obs, data/var) with werkzeug 3.x
#   Root cause: flatbuffers Python library builder.Output() returns bytearray, not bytes.
#   werkzeug 2.x accepted bytearray; werkzeug 3.x enforces bytes strictly.
#   Affected code: server/common/fbs/matrix.py encode_matrix_fbs() last line:
#     return builder.Output()  # bytearray — werkzeug 3.x rejects this
#   Fix: patch the installed file to wrap with bytes(): return bytes(builder.Output())
#   This is a one-character fix that cannot be upstreamed to cellxgene==1.3.0 (frozen tag).
#   See: https://github.com/chanzuckerberg/cellxgene/blob/1.3.0/server/common/fbs/matrix.py
RUN pip install --no-cache-dir cellxgene==1.3.0 gunicorn>=21.2 && \
    FBS_MATRIX=$(python3 -c "import server.common.fbs.matrix as m; print(m.__file__)") && \
    sed -i 's/return builder\.Output()/return bytes(builder.Output())/' "$FBS_MATRIX" && \
    echo "Patched $FBS_MATRIX" && \
    grep 'return bytes' "$FBS_MATRIX"

# cellxgene listens on 0.0.0.0:5005 (port passed via CLI args in aci_backend.py).
# We run it via gunicorn --threads to allow concurrent requests — without this,
# werkzeug serialises all requests and large binary responses (3-10MB UMAP/annotations)
# cause subsequent concurrent fetches to time out in the browser.
EXPOSE 5005

# Not used directly — ACI backend passes the full command via aci_backend.py.
ENTRYPOINT ["cellxgene"]
