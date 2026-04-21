# h5ad Compatibility Notes

## Barcodes column issue

**Symptom:** cellxgene fails to load with an error about the `barcodes` column or
obs index having unexpected format.

**Root cause:** Some h5ad files (e.g. from Seurat export) store cell barcodes in
`obs['barcodes']` as a regular column rather than in the obs index. cellxgene 1.3.0
expects the index to be the cell identifier.

**Fix:** Before uploading, reindex:

```python
import anndata as ad

adata = ad.read_h5ad("dataset.h5ad")
if "barcodes" in adata.obs.columns:
    adata.obs.index = adata.obs["barcodes"].astype(str)
    adata.obs.drop(columns=["barcodes"], inplace=True)
    adata.obs.index.name = None
adata.write_h5ad("dataset_fixed.h5ad")
```

**Affected datasets:** `umass_kent_pankbase_integrated.h5ad` (fixed Apr 2026)

## Large dataset flags

For datasets >10 GB, use `--backed` mode to memory-map the file instead of loading
it entirely into RAM. Combined with `--max-category-items` to cap dropdown sizes:

```
--backed --max-category-items 500
```

Set via `ACI_DATASET_RESOURCES`:
```json
{"pankbase": {"memory": 56, "cpu": 8, "flags": "--backed --max-category-items 500"}}
```
