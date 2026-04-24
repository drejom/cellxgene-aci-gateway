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
# The bytes assertion is a cellxgene data-encoding issue, not a werkzeug version issue.
RUN pip install --no-cache-dir cellxgene==1.3.0

# cellxgene listens on 0.0.0.0:5005 (port passed via CLI args in aci_backend.py)
EXPOSE 5005

# Not used directly — ACI backend passes the full cellxgene CLI command.
# This image just needs cellxgene on PATH.
ENTRYPOINT ["cellxgene"]
