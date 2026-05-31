"""
qsi_extract.utils.logging
===========================

Logging configuration and per-subject/session run log aggregation.

``setup_logging()``
    Configure the root ``qsi_extract`` logger based on verbosity level.

``RunLogger``
    Accumulates per-subject, per-session events (file paths found, warnings
    raised) during a run and produces a tidy DataFrame at the end.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

import pandas as pd


def setup_logging(verbosity: int = 0) -> None:
    """Configure the qsi_extract logger.

    Parameters
    ----------
    verbosity:
        0 → WARNING, 1 → INFO, 2 → DEBUG.
    """
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(verbosity, logging.DEBUG)

    logger = logging.getLogger("qsi_extract")
    if logger.handlers:
        return  # already configured (e.g. during testing)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)


class RunLogger:
    """Accumulate per-subject/session events for the run log TSV.

    Thread-safety: not thread-safe; assumes single-threaded execution.
    """

    def __init__(self) -> None:
        # Keyed by (subject, session)
        self._files: dict[tuple, dict[str, Optional[Path]]] = defaultdict(dict)
        self._warnings: dict[tuple, list[str]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_file(
        self,
        subject: str,
        session: str,
        file_type: str,
        path: Optional[Path],
    ) -> None:
        """Record a file path (or None) for a subject/session.

        Parameters
        ----------
        subject:
            Subject label.
        session:
            Session label.
        file_type:
            Logical file type string (e.g. ``"bundle_scalar"``, ``"qc"``).
        path:
            Absolute path, or ``None`` if the file was not found.
        """
        key = (subject, session)
        self._files[key][file_type] = path

    def record_warning(self, subject: str, session: str, message: str) -> None:
        """Append a warning message for a subject/session."""
        self._warnings[(subject, session)].append(message)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dataframe(self) -> pd.DataFrame:
        """Convert accumulated events to the run log DataFrame."""
        all_keys = set(self._files.keys()) | set(self._warnings.keys())
        if not all_keys:
            return pd.DataFrame(columns=[
                "subject", "session", "status",
                "bundle_scalar_file", "qc_file", "confounds_file",
                "noddi_json_found", "warnings",
            ])

        rows = []
        for subject, session in sorted(all_keys):
            key = (subject, session)
            files = self._files.get(key, {})
            warnings = self._warnings.get(key, [])

            bundle_file = files.get("bundle_scalar")
            qc_file = files.get("qc")
            confounds_file = files.get("confounds")
            noddi_json = files.get("noddi_json")

            # Determine status
            if bundle_file is not None and qc_file is not None:
                status = "ok"
            elif bundle_file is not None:
                status = "partial"  # scalars found, QC missing
            elif qc_file is not None:
                status = "partial"  # QC found, scalars missing
            else:
                status = "missing"

            if warnings:
                status = "partial" if status == "ok" else status

            rows.append({
                "subject":           subject,
                "session":           session,
                "status":            status,
                "bundle_scalar_file": str(bundle_file) if bundle_file else "",
                "qc_file":           str(qc_file) if qc_file else "",
                "confounds_file":    str(confounds_file) if confounds_file else "",
                "noddi_json_found":  noddi_json is not None,
                "warnings":          "|".join(warnings) if warnings else "",
            })

        return pd.DataFrame(rows)
