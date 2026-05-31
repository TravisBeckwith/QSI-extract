"""
qsi_extract.parsers.tractometry
=================================

Parse TractSeg/Scilpy tractometry CSV files into tidy scalar records.

TractSeg ``Tractometry.csv`` format
-------------------------------------
The standard TractSeg output from ``Tractometry -i ... -o Tractometry.csv``
is a wide CSV with:

- Row index = node position along the tract (0–99 by default, representing
  equidistant points)
- Columns = one per bundle (e.g. ``AF_left``, ``CST_right``, …)
- Values = the scalar value at that node for that bundle

One such file exists per scalar (FA, MD, etc.); they are typically named
``Tractometry_FA.csv``, ``Tractometry_MD.csv``, etc., or a single merged
file named ``Tractometry.csv``.

Scilpy tractometry format
--------------------------
Scilpy's ``scil_bundle_mean_std.py`` / ``scil_bundle_stats_profiles.py``
produces either:
- A per-bundle CSV with columns: ``label``, ``mean``, ``std`` (one row
  per node or one row total)
- A combined TSV with one row per bundle

This parser handles all variants by detecting the column structure at
runtime.

Collapse behaviour
------------------
Along-tract profiles are collapsed to per-bundle ``mean`` and ``std``
across all nodes.  This matches the output schema of ``BundleMeansParser``.
The full along-tract profile is not currently retained in the output table
(see Known Limitations in the README).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Re-use the same bundle id column names as bundle_means parser
_BUNDLE_ID_COLS = {"bundle_name", "tractname", "tract_name", "bundle", "name", "label"}


def _infer_recon_suffix(path: Path) -> str:
    for part in path.parts:
        if part.startswith("qsirecon-"):
            return part.removeprefix("qsirecon-")
    return "unknown"


def _scalar_name_from_path(path: Path) -> Optional[str]:
    """Try to infer scalar name from file name (e.g. Tractometry_FA.csv → fa)."""
    stem = path.stem.lower()
    for scalar in ("fa", "md", "ad", "rd", "icvf", "isovf", "od", "ndi", "odi", "fwf"):
        if stem.endswith("_" + scalar) or stem.endswith("-" + scalar):
            return scalar
    return None


class TractometryParser:
    """Parse a TractSeg/Scilpy tractometry CSV file.

    Parameters
    ----------
    path:
        Absolute path to the tractometry CSV.
    subject:
        Subject label.
    session:
        Session label.
    scalar_name:
        Override the scalar name.  If ``None``, inferred from the filename.
    """

    def __init__(
        self,
        path: Path,
        subject: str,
        session: str,
        scalar_name: Optional[str] = None,
    ) -> None:
        self.path = Path(path)
        self.subject = subject
        self.session = session
        self.scalar_name = scalar_name or _scalar_name_from_path(self.path) or "unknown"
        self.recon_suffix = _infer_recon_suffix(self.path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> list[dict]:
        """Parse and collapse tractometry file to per-bundle mean/std.

        Returns
        -------
        list[dict]
            One dict per (bundle, scalar) pair.
        """
        sep = "\t" if self.path.suffix == ".tsv" else ","
        try:
            df = pd.read_csv(self.path, sep=sep, dtype=str)
        except Exception as exc:
            raise ValueError(f"Could not read {self.path}: {exc}") from exc

        if df.empty:
            return []

        # Normalise column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Detect format
        if self._is_along_tract_wide(df):
            return self._parse_wide_along_tract(df)
        elif self._is_per_bundle_stats(df):
            return self._parse_per_bundle_stats(df)
        else:
            logger.warning(
                "[%s %s] Unrecognised tractometry format in %s — skipping",
                self.subject, self.session, self.path.name,
            )
            return []

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def _is_along_tract_wide(self, df: pd.DataFrame) -> bool:
        """Wide format: rows = nodes, columns = bundle names.

        Heuristics:
        - Multiple non-numeric columns (bundle names are strings)
        - OR the CSV has no 'mean'/'std'/'bundle' marker columns and
          has many columns (typical along-tract layout)
        """
        non_id_cols = [c for c in df.columns
                       if c not in _BUNDLE_ID_COLS and not c.strip().lstrip("-").replace(".", "").isdigit()]
        # If columns look like bundle names (containing underscore or known laterality markers)
        bundle_like = [c for c in non_id_cols if any(
            marker in c for marker in ("left", "right", "_l", "_r", "ca", "fx", "mcp", "af", "cst", "ifo", "ilf")
        )]
        if len(bundle_like) >= 2:
            return True
        # Fallback: many non-id columns and no explicit stats markers → likely along-tract
        stats_markers = {"mean", "std", "bundle", "tract_name", "bundle_name"}
        if len(non_id_cols) >= 2 and not stats_markers.intersection(set(df.columns)):
            return True
        return False

    def _is_per_bundle_stats(self, df: pd.DataFrame) -> bool:
        """Per-bundle stats format: columns include 'mean' or 'bundle'."""
        cols = set(df.columns)
        return bool(cols & {"mean", "std", "bundle", "tract_name", "bundle_name"})

    # ------------------------------------------------------------------
    # Parsers for each format
    # ------------------------------------------------------------------

    def _parse_wide_along_tract(self, df: pd.DataFrame) -> list[dict]:
        """Collapse wide along-tract matrix to per-bundle mean/std."""
        records: list[dict] = []

        # Drop any pure-numeric index column
        drop_cols = [c for c in df.columns if c.strip().lstrip("-").replace(".", "").isdigit()]
        df = df.drop(columns=drop_cols)

        for bundle_col in df.columns:
            values = pd.to_numeric(df[bundle_col], errors="coerce").dropna()
            if values.empty:
                continue
            bundle = bundle_col.strip().lower().replace(" ", "_").replace("-", "_")
            mean_val = float(values.mean())
            std_val = float(values.std())

            for stat, val in [("mean", mean_val), ("std", std_val)]:
                records.append({
                    "subject":      self.subject,
                    "session":      self.session,
                    "bundle":       bundle,
                    "scalar":       f"{self.scalar_name}_{stat}",
                    "scalar_raw":   bundle_col,
                    "value":        val,
                    "bundle_source": "tractometry",
                    "recon_suffix": self.recon_suffix,
                    "is_shape_stat": False,
                    "n_nodes":      len(values),
                })

        return records

    def _parse_per_bundle_stats(self, df: pd.DataFrame) -> list[dict]:
        """Parse a pre-summarised per-bundle stats table."""
        records: list[dict] = []

        bundle_col = next(
            (c for c in df.columns if c in {"bundle", "tract_name", "bundle_name", "tractname"}),
            df.columns[0],
        )

        for _, row in df.iterrows():
            bundle_raw = str(row.get(bundle_col, ""))
            if not bundle_raw or bundle_raw.lower() == "nan":
                continue
            bundle = bundle_raw.strip().lower().replace(" ", "_").replace("-", "_")

            for stat in ("mean", "std"):
                if stat not in df.columns:
                    continue
                try:
                    value = float(row[stat])
                except (ValueError, TypeError):
                    continue
                records.append({
                    "subject":      self.subject,
                    "session":      self.session,
                    "bundle":       bundle,
                    "scalar":       f"{self.scalar_name}_{stat}",
                    "scalar_raw":   stat,
                    "value":        value,
                    "bundle_source": "tractometry",
                    "recon_suffix": self.recon_suffix,
                    "is_shape_stat": False,
                })

        return records
