"""
qsi_extract.collators.metadata
================================

Propagate pipeline version metadata into the primary table.

Reads ``dataset_description.json`` from the QSIPrep and QSIRecon derivative
datasets (discovered by ``BIDSLayout``) and adds ``qsiprep_version`` and
``qsirecon_version`` columns to the output DataFrame.

Also reads ``<subject>_sessions.tsv`` to populate ``session_age_months``
where available — critical for the NODDI infant assumption audit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from qsi_extract.layout.bids_layout import BIDSLayout

logger = logging.getLogger(__name__)


class MetadataCollator:
    """Attach pipeline version and session age metadata to the main table.

    Parameters
    ----------
    layout:
        A fully discovered ``BIDSLayout`` instance.
    """

    def __init__(self, layout: BIDSLayout) -> None:
        self.layout = layout

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add version and age columns to *df* in-place and return it."""
        df = self._add_versions(df)
        df = self._add_session_ages(df)
        return df

    # ------------------------------------------------------------------
    # Version propagation
    # ------------------------------------------------------------------

    def _add_versions(self, df: pd.DataFrame) -> pd.DataFrame:
        qsiprep_version = self._extract_version(self.layout.qsiprep_dataset_desc)
        df["qsiprep_version"] = qsiprep_version

        # QSIRecon: pick the first suffix's version (they should all match)
        qsirecon_version = "unknown"
        for _suffix, desc in self.layout.qsirecon_dataset_descs.items():
            v = self._extract_version(desc)
            if v != "unknown":
                qsirecon_version = v
                break
        df["qsirecon_version"] = qsirecon_version

        return df

    @staticmethod
    def _extract_version(desc: dict) -> str:
        """Pull version string from a dataset_description.json dict."""
        if not desc:
            return "unknown"
        # Standard BIDS: GeneratedBy[0].Version
        generated_by = desc.get("GeneratedBy", [])
        if generated_by and isinstance(generated_by, list):
            v = generated_by[0].get("Version", "")
            if v:
                return str(v)
        # Fallback: top-level "Version"
        return str(desc.get("Version", "unknown"))

    # ------------------------------------------------------------------
    # Session age propagation
    # ------------------------------------------------------------------

    def _add_session_ages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ``session_age_months`` by reading sessions TSV files."""
        if "subject" not in df.columns or "session" not in df.columns:
            return df

        age_map: dict[tuple[str, str], float] = {}

        for subject in df["subject"].unique():
            tsv_path = self.layout.get_sessions_tsv(subject)
            if tsv_path is None:
                continue
            try:
                tsv = pd.read_csv(tsv_path, sep="\t")
                tsv.columns = [c.strip().lower() for c in tsv.columns]
            except Exception as exc:
                logger.warning("[%s] Could not read sessions TSV: %s", subject, exc)
                continue

            # Identify age column
            age_col = None
            for candidate in ("age_months", "age", "age_in_months"):
                if candidate in tsv.columns:
                    age_col = candidate
                    break

            if age_col is None:
                logger.debug("[%s] No age column found in sessions TSV", subject)
                continue

            # Identify session column
            ses_col = None
            for candidate in ("session_id", "session", "ses"):
                if candidate in tsv.columns:
                    ses_col = candidate
                    break

            if ses_col is None:
                continue

            for _, row in tsv.iterrows():
                ses_raw = str(row[ses_col]).strip()
                # Normalise: ensure "ses-" prefix
                session = ses_raw if ses_raw.startswith("ses-") else f"ses-{ses_raw}"
                try:
                    age = float(row[age_col])
                    age_map[(subject, session)] = age
                except (ValueError, TypeError):
                    pass

        if not age_map:
            df["session_age_months"] = float("nan")
            return df

        df["session_age_months"] = df.apply(
            lambda r: age_map.get((r["subject"], r["session"]), float("nan")),
            axis=1,
        )
        return df
