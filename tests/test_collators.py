"""Tests for qsi_extract.collators.longitudinal."""

from __future__ import annotations

import math
import pandas as pd
import pytest

from qsi_extract.collators.longitudinal import LongitudinalCollator


def make_scalar_records():
    """Minimal scalar records for two subjects, one session, two bundles."""
    records = []
    for sub in ("sub-01", "sub-02"):
        for bundle in ("af_left", "cst_left"):
            for scalar, val in [("fa_mean", 0.38), ("icvf_mean", 0.42)]:
                records.append({
                    "subject": sub,
                    "session": "ses-1mo",
                    "bundle": bundle,
                    "scalar": scalar,
                    "value": val,
                    "bundle_source": "bundle_means",
                    "recon_suffix": "NODDI",
                })
    return records


class TestLongitudinalCollator:
    def test_returns_dataframe(self):
        records = make_scalar_records()
        df = LongitudinalCollator().collate(
            scalar_records=records,
            sidecar_records=[],
            qc_records=[],
            all_subjects=["sub-01", "sub-02"],
            all_sessions=["ses-1mo"],
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_complete_grid_has_missing_gaps(self):
        """sub-01 ses-6mo should be in the grid (NaN) even without records."""
        records = make_scalar_records()  # only ses-1mo
        df = LongitudinalCollator().collate(
            scalar_records=records,
            sidecar_records=[],
            qc_records=[],
            all_subjects=["sub-01"],
            all_sessions=["ses-1mo", "ses-6mo"],
        )
        ses_6mo = df[df["session"] == "ses-6mo"]
        assert len(ses_6mo) > 0
        assert not ses_6mo["scalar_present"].any()
        assert ses_6mo["value"].isna().all()

    def test_scalar_present_true_for_found(self):
        records = make_scalar_records()
        df = LongitudinalCollator().collate(
            scalar_records=records, sidecar_records=[], qc_records=[],
            all_subjects=["sub-01"], all_sessions=["ses-1mo"],
        )
        found = df[(df["subject"] == "sub-01") & (df["session"] == "ses-1mo")]
        assert found["scalar_present"].all()

    def test_sidecar_broadcast_per_session(self):
        """Sidecar d_par should appear on every bundle row for that session."""
        import numpy as np
        records = make_scalar_records()
        sidecar = [{"subject": "sub-01", "session": "ses-1mo", "noddi_d_par": 1.7}]
        df = LongitudinalCollator().collate(
            scalar_records=records, sidecar_records=sidecar, qc_records=[],
            all_subjects=["sub-01"], all_sessions=["ses-1mo"],
        )
        sub01 = df[(df["subject"] == "sub-01") & (df["scalar_present"])]
        assert np.allclose(sub01["noddi_d_par"].values, 1.7)

    def test_qc_broadcast_per_session(self):
        import numpy as np
        records = make_scalar_records()
        qc = [{"subject": "sub-01", "session": "ses-1mo", "qc_mean_fd": 0.35}]
        df = LongitudinalCollator().collate(
            scalar_records=records, sidecar_records=[], qc_records=qc,
            all_subjects=["sub-01"], all_sessions=["ses-1mo"],
        )
        sub01 = df[(df["subject"] == "sub-01") & (df["scalar_present"])]
        assert np.allclose(sub01["qc_mean_fd"].values, 0.35)

    def test_wide_format_pivot(self):
        records = make_scalar_records()
        df = LongitudinalCollator(scalar_format="wide").collate(
            scalar_records=records, sidecar_records=[], qc_records=[],
            all_subjects=["sub-01"], all_sessions=["ses-1mo"],
        )
        # In wide format, scalar names become column names
        assert "fa_mean" in df.columns or "icvf_mean" in df.columns

    def test_missing_session_policy_error(self):
        """Records exist but all for a different session — target ses-6mo has no data."""
        records = make_scalar_records()  # all ses-1mo
        collator = LongitudinalCollator(missing_session_policy="error")
        with pytest.raises(RuntimeError):
            collator.collate(
                scalar_records=records,
                sidecar_records=[],
                qc_records=[],
                all_subjects=["sub-01"],
                all_sessions=["ses-1mo", "ses-6mo"],  # ses-6mo has no records
            )

    def test_priority_columns_appear_first(self):
        records = make_scalar_records()
        df = LongitudinalCollator().collate(
            scalar_records=records, sidecar_records=[], qc_records=[],
            all_subjects=["sub-01"], all_sessions=["ses-1mo"],
        )
        first_cols = list(df.columns[:4])
        assert first_cols == ["subject", "session", "bundle", "scalar"]
