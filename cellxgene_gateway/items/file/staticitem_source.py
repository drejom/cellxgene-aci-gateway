# StaticItemSource — drives the gateway UI from an explicit allowlist of filenames.
# Set CELLXGENE_DATASETS=file1.h5ad,file2.h5ad (comma-separated).
# No filesystem scan; works when datasets live on Azure Files (not locally mounted).

import os

from cellxgene_gateway.items.file.fileitem import FileItem
from cellxgene_gateway.items.item import ItemTree, ItemType
from cellxgene_gateway.items.item_source import ItemSource, LookupResult


class StaticItemSource(ItemSource):
    def __init__(self, datasets: list[str], name: str = "static"):
        """
        datasets: list of bare filenames, e.g. ['foo.h5ad', 'bar.h5ad']
        """
        self._name = name
        self._datasets = datasets

    @property
    def name(self):
        return self._name

    def list_items(self, filter: str = None) -> ItemTree:
        items = [
            FileItem(subpath="", name=ds, ext="", type=ItemType.h5ad)
            for ds in self._datasets
            if filter is None or filter in ds
        ]
        return ItemTree("", items, None)

    def lookup(self, descriptor: str) -> LookupResult:
        descriptor = descriptor.strip("/")
        for ds in self._datasets:
            if descriptor == ds:
                item = FileItem(subpath="", name=ds, ext="", type=ItemType.h5ad)
                return LookupResult(item)
        return None

    def is_authorized(self, descriptor):
        return descriptor.strip("/") in self._datasets

    def get_local_path(self, item: FileItem) -> str:
        # No local path — datasets are on Azure Files, accessed by ACI directly.
        return item.descriptor

    def get_annotations_subpath(self, item) -> str:
        return ""

    def create_annotation(self, item: FileItem, name: str) -> FileItem:
        raise NotImplementedError("Annotations not supported with static item source")

    def update(self, item: FileItem) -> None:
        pass
