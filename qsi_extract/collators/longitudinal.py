"""
qsi_extract.collators.longitudinal
=====================================

Assemble the primary longitudinal table from parsed records.

The collation strategy is:

1. Build the complete **subject × session × bundle × scalar grid** from all
   discovered entities.  This ensures every possible cell exists in the
   output, even if the underlying data was absent (gaps appear as NaN).

2. Left-join scalar records onto the grid.

3. Left-join NODDI sidecar params (one per sub/ses) onto the result,
   broadcasting across all bundles for that session.

4. Left-join QC records (one per sub/ses) similarly.

5. Add ``scalar_present`` boolean column to distinguish true NaN values
   from missing data.

6. Optionally pivot to wide format (one row per sub × ses × bundle).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Index columns that uniquely identify a scalar row in long format
_LONG_INDEX = ["subject", "session", "bundle", "scalar"]

# Index columns shared between all sources (joined on these)
_SESSION_INDEX = ["subject", "session"]
_BUNDLE_INDEX  = ["subject", "session", "bundle"]


class LongitudinalCollator:
    """Collate parsed records into a tidy longitudinal DataFrame.

    Parameters
    ----------
    scalar_format:
        ``"long"`` or ``"wide"``.
    missing_session_policy:
        ``"warn"``, ``"error"``, or ``"ignore"``.
    run_logger:
        Optional ``RunLogger`` instance for recording per-subject warnings.
    """

    def __init__(
        self,
        scalar_format: str = "long",
        missing_session_policy: str = "warn",
        run_logger=None,
    ) -> None:
        self.scalar_format = scalar_format
        self.missing_session_policy = missing_session_policy
        self._run_logger = run_logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collate(
        self,
        scalar_records: list[dict],
        sidecar_records: list[dict],
        qc_records: list[dict],
        all_subjects: list[str],
        all_sessions: list[str],
    ) -> pd.DataFrame:
        """Merge all parsed records into the primary longitudinal table.

        Parameters
        ----------
        scalar_records:
            Output of ``BundleMeansParser`` or ``TractometryParser``.
        sidecar_records:
            Output of ``DwimapJsonParser`` (one per sub/ses).
        qc_records:
            Output of ``QCParser`` (one per sub/ses).
        all_subjects:
            Complete list of discovered subject labels.
        all_sessions:
            Complete list of discovered session labels.

        Returns
        -------
        pd.DataFrame
            Long or wide format depending on ``self.scalar_format``.
        """
        if not scalar_records:
            logger.warning("No scalar records to collate — output will be empty")
            return pd.DataFrame()

        # ----------------------------------------------------------
        # Step 1: Build scalar DataFrame
        # ----------------------------------------------------------
        scalar_df = pd.DataFrame(scalar_records)
        scalar_df["scalar_present"] = True

        # ----------------------------------------------------------
        # Step 2: Build the complete grid and outer-join scalars
        # ----------------------------------------------------------
        # Derive the full set of bundles and scalars from what was parsed
        all_bundles = sorted(scalar_df["bundle"].unique())
        all_scalars = sorted(scalar_df["scalar"].unique())

        grid = _build_grid(all_subjects, all_sessions, all_bundles, all_scalars)
        df = grid.merge(scalar_df, on=_LONG_INDEX, how="left")
        df["scalar_present"] = df["scalar_present"].fillna(False)

        # ----------------------------------------------------------
        # Step 3: Propagate session-level sidecar metadata
        # ----------------------------------------------------------
        if sidecar_records:
            sidecar_df = pd.DataFrame(sidecar_records).drop_duplicates(_SESSION_INDEX)
            df = df.merge(sidecar_df, on=_SESSION_INDEX, how="left")

        # ----------------------------------------------------------
        # Step 4: Propagate session-level QC
        # ----------------------------------------------------------
        if qc_records:
            qc_df = pd.DataFrame(qc_records).drop_duplicates(_SESSION_INDEX)
            df = df.merge(qc_df, on=_SESSION_INDEX, how="left")

        # ----------------------------------------------------------
        # Step 5: Log and handle missing sessions
        # ----------------------------------------------------------
        self._handle_missing(df, all_subjects, all_sessions)

        # ----------------------------------------------------------
        # Step 6: Column ordering and dtype tidying
        # ----------------------------------------------------------
        df = _tidy_dtypes(df)
        df = _reorder_columns(df)

        # ----------------------------------------------------------
        # Step 7: Wide format pivot (optional)
        # ----------------------------------------------------------
        if self.scalar_format == "wide":
            df = self._pivot_wide(df)

        logger.info("Collation complete: %d rows × %d columns", len(df), len(df.columns))
        return df

    # ------------------------------------------------------------------
    # Wide pivot
    # ------------------------------------------------------------------

    def _pivot_wide(self, df: pd.DataFrame) -> pd.DataFrame:
        """Pivot long scalar rows into wide format."""
        # Columns that should stay as index (not pivoted)
        meta_cols = [c for c in df.columns
                     if c not in ("scalar", "value", "scalar_raw", "is_shape_stat", "scalar_present")]

        try:
            wide = df.pivot_table(
                index=_BUNDLE_INDEX,
                columns="scalar",
                values="value",
                aggfunc="first",
            ).reset_index()
            wide.columns.name = None

            # Re-attach session-level metadata (take first non-null per sub/ses/bundle)
            meta_unique = df.groupby(_BUNDLE_INDEX)[
                [c for c in meta_cols if c not in _BUNDLE_INDEX]
            ].first().reset_index()

            wide = wide.merge(meta_unique, on=_BUNDLE_INDEX, how="left")
        except Exception as exc:
            logger.warning("Wide pivot failed (%s); returning long format", exc)
            return df

        return wide

    # ------------------------------------------------------------------
    # Missing data handling
    # ------------------------------------------------------------------

    def _handle_missing(
        self, df: pd.DataFrame, all_subjects: list[str], all_sessions: list[str]
    ) -> None:
        """Log or raise for sessions with entirely missing scalar data."""
        for subject in all_subjects:
            for session in all_sessions:
                mask = (df["subject"] == subject) & (df["session"] == session)
                subset = df[mask]
                if subset.empty:
                    continue
                n_present = subset["scalar_present"].sum()
                if n_present == 0:
                    msg = f"No scalar data found for {subject} {session}"
                    if self.missing_session_policy == "error":
                        raise RuntimeError(msg)
                    elif self.missing_session_policy == "warn":
                        logger.warning(msg)
                        if self._run_logger:
                            self._run_logger.record_warning(subject, session, "no_scalar_data")
                    # "ignore": do nothing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_grid(
    subjects: list[str],
    sessions: list[str],
    bundles: list[str],
    scalars: list[str],
) -> pd.DataFrame:
    """Build the complete subject × session × bundle × scalar index."""
    import itertools
    rows = list(itertools.product(subjects, sessions, bundles, scalars))
    return pd.DataFrame(rows, columns=_LONG_INDEX)


def _tidy_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric columns and fill companion booleans."""
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if "scalar_present" in df.columns:
        df["scalar_present"] = df["scalar_present"].fillna(False).astype(bool)
    if "noddi_modulated_present" in df.columns:
        df["noddi_modulated_present"] = df["noddi_modulated_present"].fillna(False).astype(bool)
    return df


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Put the most important columns first."""
    priority = [
        "subject", "session", "bundle", "scalar", "value", "scalar_present",
        "recon_suffix", "bundle_source",
        "noddi_d_par", "noddi_d_par_flag", "noddi_d_iso", "noddi_modulated_present",
        "qc_mean_fd", "qc_max_fd", "qc_ndc", "qc_num_bad_slices",
        "qc_n_volumes", "qc_n_censored", "qc_pct_censored",
    ]
    present_priority = [c for c in priority if c in df.columns]
    remaining = [c for c in df.columns if c not in present_priority]
    return df[present_priority + remaining]
