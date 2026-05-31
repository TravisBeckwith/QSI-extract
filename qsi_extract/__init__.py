"""
qsi_extract
===========

Extract and collate diffusion MRI scalar outputs from QSIPrep and QSIRecon
into tidy longitudinal tabular datasets.

Typical usage
-------------
>>> from qsi_extract import Extractor
>>> from qsi_extract.config import ExtractorConfig
>>>
>>> config = ExtractorConfig(
...     qsiprep_dir="/data/derivatives/qsiprep",
...     qsirecon_dir="/data/derivatives/qsirecon",
...     output_dir="/data/derivatives/qsi_extract",
... )
>>> extractor = Extractor(config)
>>> df = extractor.run()

See Also
--------
qsi_extract.cli      : Command-line entry point
qsi_extract.config   : ExtractorConfig dataclass
qsi_extract.layout   : BIDS directory traversal
qsi_extract.parsers  : Per-file-type scalar parsers
qsi_extract.collators: Longitudinal table assembly
qsi_extract.flags    : NODDI assumption auditing
qsi_extract.output   : Writers and data dictionary
"""

from __future__ import annotations

try:
    from qsi_extract._version import version as __version__
except ImportError:  # package not installed via setuptools-scm
    __version__ = "0.0.0+unknown"

from qsi_extract._extractor import Extractor

__all__ = [
    "__version__",
    "Extractor",
]
