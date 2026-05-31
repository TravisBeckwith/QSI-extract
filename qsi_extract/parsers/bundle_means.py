"""
qsi_extract.parsers.bundle_means
==================================

Parse QSIRecon bundle-level scalar summary files into a list of tidy dicts.

Supported formats
-----------------
``bundle_means.tsv``
    Produced by a custom ``bundle_map`` node.  Wide format: one row per
    bundle, columns like ``mean_fa``, ``std_fa``, ``mean_icvf``, etc.
    The first column is always ``bundle_name``.

``*_scalarstats.csv``
    Produced by DSI Studio autotrack (``dsi_studio_autotrack``,
    ``hbcd_scalar_maps``).  Wide format: one row per bundle.  Columns
    include scalars like ``dti_fa``, ``gfa``, ``qa``, ``iso``,
    ``mean_length``, ``volume``, etc.  First column is typically the
    bundle name or track name.

Both formats are normalised to the same internal long-format records::

    [
        {
            "subject": "sub-01",
            "session": "ses-1mo",
            "bundle":  "AF_left",
            "scalar":  "fa_mean",
            "value":   0.38,
            "bundle_source": "bundle_means",
            "recon_suffix":  "NODDI",
        },
        ...
    ]

Bundle name normalisation
-------------------------
Bundle names are lowercased and spaces are replaced with underscores to
produce consistent identifiers regardless of which tool generated the file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Columns that identify the bundle row rather than carry scalar data.
# These are dropped before melting to long format.
_BUNDLE_ID_COLS = {"bundle_name", "tractname", "tract_name", "bundle", "name"}

# Columns from DSI Studio autotrack that are shape statistics rather than
# diffusion scalars.  We keep them (they're scientifically useful) but tag
# them separately so they can be filtered downstream.
_SHAPE_COLS = {
    "mean_length", "span", "curl", "volume", "endpoint_radius",
    "ncount", "pcount", "step_resolution",
}


def _normalise_bundle_name(name: str) -> str:
    """Lower-case, strip, replace spaces/hyphens with underscores."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _infer_bundle_col(df: pd.DataFrame) -> str:
    """Return the name of the column that contains bundle identifiers."""
    for candidate in _BUNDLE_ID_COLS:
        if candidate in df.columns:
            return candidate
    # Fall back to first column
    return df.columns[0]


def _infer_recon_suffix(path: Path) -> str:
    """Extract the QSIRecon suffix from the file path.

    Expects a path like:
        .../qsirecon-NODDI/sub-01/ses-1mo/dwi/*_bundle_means.tsv
    """
    for part in path.parts:
        if part.startswith("qsirecon-"):
            return part.removeprefix("qsirecon-")
    return "unknown"


class BundleMeansParser:
    """Parse a ``bundle_means.tsv`` or ``*_scalarstats.csv`` file.

    Parameters
    ----------
    path:
        Absolute path to the file.
    subject:
        Subject label (e.g. ``"sub-01"``).
    session:
        Session label (e.g. ``"ses-1mo"``), or ``"_no_session"``.
    source_type:
        ``"bundle_means"`` or ``"scalarstats"``; inferred from filename
        if not provided.
    """

    def __init__(
        self,
        path: Path,
        subject: str,
        session: str,
        source_type: Optional[str] = None,
    ) -> None:
        self.path = Path(path)
        self.subject = subject
        self.session = session
        self.source_type = source_type or self._infer_source_type()
        self.recon_suffix = _infer_recon_suffix(self.path)

    def _infer_source_type(self) -> str:
        name = self.path.name.lower()
        if "bundle_means" in name:
            return "bundle_means"
        if "scalarstats" in name:
            return "scalarstats"
        return "bundle_means"  # safe default

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> list[dict]:
        """Parse the file and return a list of tidy scalar records.

        Returns
        -------
        list[dict]
            One dict per (bundle, scalar) combination.

        Raises
        ------
        ValueError
            If the file cannot be parsed or contains no usable data.
        """
        sep = "\t" if self.path.suffix == ".tsv" else ","
        try:
            df = pd.read_csv(self.path, sep=sep, dtype=str)
        except Exception as exc:
            raise ValueError(f"Could not read {self.path}: {exc}") from exc

        if df.empty:
            logger.warning("[%s %s] Bundle scalar file is empty: %s", self.subject, self.session, self.path.name)
            return []

        # Normalise column names: lowercase, strip whitespace
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        bundle_col = _infer_bundle_col(df)
        scalar_cols = [c for c in df.columns if c != bundle_col]

        if not scalar_cols:
            logger.warning("[%s %s] No scalar columns found in %s", self.subject, self.session, self.path.name)
            return []

        records: list[dict] = []
        for _, row in df.iterrows():
            bundle_raw = str(row[bundle_col])
            if not bundle_raw or bundle_raw.lower() in ("nan", ""):
                continue
            bundle = _normalise_bundle_name(bundle_raw)

            for col in scalar_cols:
                raw_val = row[col]
                try:
                    # Explicit rejection of common NA string representations
                    if str(raw_val).strip().lower() in ("", "nan", "na", "n/a", "none", "null", "."):
                        continue
                    value = float(raw_val)
                except (ValueError, TypeError):
                    continue  # skip non-numeric cells

                # Normalise column name to canonical scalar name.
                # bundle_means.tsv already uses mean_<param> convention.
                # scalarstats.csv uses <model>_<param> (e.g. dti_fa).
                # We standardise to <param>_mean for the scalar name,
                # keeping the raw column name as scalar_raw for traceability.
                scalar_name = _normalise_scalar_name(col, self.source_type)

                records.append({
                    "subject":      self.subject,
                    "session":      self.session,
                    "bundle":       bundle,
                    "scalar":       scalar_name,
                    "scalar_raw":   col,
                    "value":        value,
                    "bundle_source": self.source_type,
                    "recon_suffix": self.recon_suffix,
                    "is_shape_stat": col in _SHAPE_COLS,
                })

        logger.debug(
            "[%s %s] Parsed %d records from %s",
            self.subject, self.session, len(records), self.path.name,
        )
        return records


# ---------------------------------------------------------------------------
# Scalar name normalisation
# ---------------------------------------------------------------------------

# Maps known raw column name variants → canonical name
_SCALAR_NAME_MAP: dict[str, str] = {
    # bundle_means.tsv style (already normalised, just confirm)
    "mean_fa":   "fa_mean",
    "mean_md":   "md_mean",
    "mean_ad":   "ad_mean",
    "mean_rd":   "rd_mean",
    "mean_icvf": "icvf_mean",
    "mean_isovf": "isovf_mean",
    "mean_od":   "od_mean",
    "std_fa":    "fa_std",
    "std_md":    "md_std",
    "std_icvf":  "icvf_std",
    # scalarstats.csv / DSI Studio style
    "dti_fa":    "fa_mean",
    "dti_md":    "md_mean",
    "dti_ad":    "ad_mean",
    "dti_rd":    "rd_mean",
    "gfa":       "gfa_mean",
    "qa":        "qa_mean",
    "iso":       "iso_mean",
    "rdi":       "rdi_mean",
}


def _normalise_scalar_name(raw_col: str, source_type: str) -> str:
    """Convert a raw column name to a canonical scalar name.

    Falls back to ``<raw_col>_mean`` for unknown column names from
    ``bundle_means`` files and ``<raw_col>`` unchanged for shape stats.
    """
    col = raw_col.lower().strip()

    if col in _SCALAR_NAME_MAP:
        return _SCALAR_NAME_MAP[col]

    # bundle_means convention: mean_X → X_mean, std_X → X_std
    if col.startswith("mean_"):
        return col[5:] + "_mean"
    if col.startswith("std_"):
        return col[4:] + "_std"

    # Shape stats stay as-is
    if col in _SHAPE_COLS:
        return col

    # Unknown: return as-is and let downstream decide
    return col
