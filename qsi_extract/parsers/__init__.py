"""Per-file-type scalar parsers — each returns ``list[dict]``."""

from qsi_extract.parsers.bundle_means import BundleMeansParser
from qsi_extract.parsers.tractometry import TractometryParser
from qsi_extract.parsers.dwimap_json import DwimapJsonParser
from qsi_extract.parsers.qc import QCParser

__all__ = [
    "BundleMeansParser",
    "TractometryParser",
    "DwimapJsonParser",
    "QCParser",
]
