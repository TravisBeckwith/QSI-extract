"""
qsi_extract.parsers.qc
========================

Parse QSIPrep and MRIQC QC files into per-session metric records.

Sources
-------
``*_desc-image_qc.tsv`` (QSIPrep ≥1.0)
``*_desc-ImageQC_dwi.csv`` (QSIPrep <1.0)
    Per-scan QC summary: neighboring DWI correlation (NDC), framewise
    displacement summaries, bad slice counts, and registration dice
    distances.

``*_desc-confounds_timeseries.tsv``
    Per-volume motion parameters.  Used to compute:
    - ``qc_n_censored``    — volumes with FD > threshold
    - ``qc_pct_censored``  — fraction of volumes censored
    - ``qc_n_volumes``     — total DWI volumes

``mriqc/dwi_group.tsv`` (optional)
    MRIQC group IQMs; all columns propagated with ``mriqc_`` prefix.

Output schema
-------------
One record per (subject, session)::

    {
        "subject": "sub-01",
        "session": "ses-1mo",
        "qc_mean_fd": 0.42,
        "qc_max_fd": 1.1,
        "qc_ndc": 0.85,
        "qc_num_bad_slices": 2,
        "qc_max_translation": 1.3,
        "qc_max_rotation": 0.02,
        "qc_t1_dice_distance": 0.04,
        "qc_n_volumes": 99,
        "qc_n_censored": 7,
        "qc_pct_censored": 0.071,
        "qc_fd_threshold_used": 0.5,
        ...mriqc columns with mriqc_ prefix...
    }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Columns from desc-image_qc.tsv / desc-ImageQC_dwi.csv to extract,
# mapped to their canonical output name.
_IMAGE_QC_COLUMNS: dict[str, str] = {
    # Current (≥1.0) column names
    "mean_fd":              "qc_mean_fd",
    "max_fd":               "qc_max_fd",
    "raw_neighbor_corr":    "qc_ndc_raw",
    "t1_neighbor_corr":     "qc_ndc",
    "raw_num_bad_slices":   "qc_num_bad_slices_raw",
    "t1_num_bad_slices":    "qc_num_bad_slices",
    "max_translation":      "qc_max_translation",
    "max_rotation":         "qc_max_rotation",
    "max_rel_translation":  "qc_max_rel_translation",
    "max_rel_rotation":     "qc_max_rel_rotation",
    "t1_dice_distance":     "qc_t1_dice_distance",
    "mni_dice_distance":    "qc_mni_dice_distance",
    # Legacy (<1.0) alternate names — mapped to same canonical names
    "neighbor_corr":        "qc_ndc",
    "num_bad_slices":       "qc_num_bad_slices",
}


class QCParser:
    """Parse QC files for a single subject/session.

    Parameters
    ----------
    qc_path:
        Path to ``*_desc-image_qc.tsv`` or ``*_desc-ImageQC_dwi.csv``.
        May be ``None`` if not found.
    confounds_path:
        Path to ``*_desc-confounds_timeseries.tsv``.  May be ``None``.
    mriqc_dir:
        Root of MRIQC derivatives.  The ``dwi_group.tsv`` inside will be
        searched for matching subject/session rows.
    subject:
        Subject label.
    session:
        Session label.
    fd_threshold:
        Framewise displacement threshold (mm) for censoring computation.
    """

    def __init__(
        self,
        qc_path: Optional[Path],
        confounds_path: Optional[Path],
        mriqc_dir: Optional[Path],
        subject: str,
        session: str,
        fd_threshold: float = 0.5,
    ) -> None:
        self.qc_path = Path(qc_path) if qc_path else None
        self.confounds_path = Path(confounds_path) if confounds_path else None
        self.mriqc_dir = Path(mriqc_dir) if mriqc_dir else None
        self.subject = subject
        self.session = session
        self.fd_threshold = fd_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> list[dict]:
        """Return a single-element list with one QC record.

        Returns an empty list if no QC source was available.
        """
        record: dict = {
            "subject": self.subject,
            "session": self.session,
        }

        any_data = False

        if self.qc_path is not None:
            qc_data = self._parse_image_qc()
            if qc_data:
                record.update(qc_data)
                any_data = True

        if self.confounds_path is not None:
            cens_data = self._parse_confounds()
            if cens_data:
                record.update(cens_data)
                any_data = True

        if self.mriqc_dir is not None:
            mriqc_data = self._parse_mriqc()
            if mriqc_data:
                record.update(mriqc_data)
                any_data = True

        return [record] if any_data else []

    # ------------------------------------------------------------------
    # Image QC parsing
    # ------------------------------------------------------------------

    def _parse_image_qc(self) -> dict:
        """Parse desc-image_qc.tsv or desc-ImageQC_dwi.csv."""
        sep = "\t" if self.qc_path.suffix == ".tsv" else ","
        try:
            df = pd.read_csv(self.qc_path, sep=sep, nrows=1)
        except Exception as exc:
            logger.warning("[%s %s] Could not read QC file %s: %s",
                           self.subject, self.session, self.qc_path.name, exc)
            return {}

        if df.empty:
            return {}

        # Normalise column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        result: dict = {}
        for raw_col, canonical in _IMAGE_QC_COLUMNS.items():
            if raw_col in df.columns:
                val = df[raw_col].iloc[0]
                try:
                    result[canonical] = float(val)
                except (ValueError, TypeError):
                    result[canonical] = float("nan")

        return result

    # ------------------------------------------------------------------
    # Confounds / censoring computation
    # ------------------------------------------------------------------

    def _parse_confounds(self) -> dict:
        """Compute censoring metrics from the confounds timeseries TSV."""
        try:
            df = pd.read_csv(self.confounds_path, sep="\t")
        except Exception as exc:
            logger.warning("[%s %s] Could not read confounds %s: %s",
                           self.subject, self.session, self.confounds_path.name, exc)
            return {}

        if "framewise_displacement" not in df.columns:
            logger.debug("[%s %s] No framewise_displacement column in confounds",
                         self.subject, self.session)
            return {}

        fd = pd.to_numeric(df["framewise_displacement"], errors="coerce")
        n_volumes = len(fd)
        n_censored = int((fd > self.fd_threshold).sum())
        pct_censored = n_censored / n_volumes if n_volumes > 0 else float("nan")

        return {
            "qc_n_volumes":         n_volumes,
            "qc_n_censored":        n_censored,
            "qc_pct_censored":      round(pct_censored, 6),
            "qc_fd_threshold_used": self.fd_threshold,
        }

    # ------------------------------------------------------------------
    # MRIQC group TSV
    # ------------------------------------------------------------------

    def _parse_mriqc(self) -> dict:
        """Extract this subject/session's row from mriqc/dwi_group.tsv."""
        group_tsv = self.mriqc_dir / "dwi_group.tsv"
        if not group_tsv.exists():
            logger.debug("MRIQC group TSV not found: %s", group_tsv)
            return {}

        try:
            df = pd.read_csv(group_tsv, sep="\t")
        except Exception as exc:
            logger.warning("Could not read MRIQC group TSV: %s", exc)
            return {}

        df.columns = [c.strip().lower() for c in df.columns]

        # Match on subject and session
        sub_label = self.subject.removeprefix("sub-")
        ses_label = self.session.removeprefix("ses-")

        mask = pd.Series([True] * len(df))
        if "subject_id" in df.columns:
            mask &= df["subject_id"].astype(str).str.replace("sub-", "") == sub_label
        elif "bids_name" in df.columns:
            mask &= df["bids_name"].astype(str).str.contains(self.subject)

        if "session_id" in df.columns and ses_label != "_no_session":
            mask &= df["session_id"].astype(str).str.replace("ses-", "") == ses_label

        rows = df[mask]
        if rows.empty:
            logger.debug("[%s %s] No MRIQC row found", self.subject, self.session)
            return {}

        row = rows.iloc[0]
        result: dict = {}
        skip_cols = {"subject_id", "session_id", "bids_name", "task_id", "run_id"}
        for col, val in row.items():
            if col in skip_cols:
                continue
            try:
                result[f"mriqc_{col}"] = float(val)
            except (ValueError, TypeError):
                result[f"mriqc_{col}"] = val  # keep string values

        return result
