"""Tests for qsi_extract.flags.noddi_assumptions."""

from __future__ import annotations

import math
import pandas as pd
import pytest

from qsi_extract.flags.noddi_assumptions import NODDIAssumptionFlagger


def make_df(**kwargs) -> pd.DataFrame:
    """Helper: build a minimal single-row DataFrame."""
    defaults = {"subject": "sub-01", "session": "ses-1mo", "bundle": "AF_left"}
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


class TestNODDIAssumptionFlagger:

    def test_infant_adult_default_warns(self):
        df = make_df(noddi_d_par=1.7, session_age_months=1.0)
        result = NODDIAssumptionFlagger(infant_threshold_months=18).apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "WARN:adult_default_d_par_in_infant"

    def test_adult_default_no_age_info(self):
        df = make_df(noddi_d_par=1.7, session_age_months=float("nan"))
        result = NODDIAssumptionFlagger(infant_threshold_months=18).apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "INFO:adult_default_d_par"

    def test_adult_default_above_threshold(self):
        df = make_df(noddi_d_par=1.7, session_age_months=36.0)
        result = NODDIAssumptionFlagger(infant_threshold_months=18).apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "INFO:adult_default_d_par"

    def test_custom_d_par_matches_expected(self):
        df = make_df(noddi_d_par=1.5, session_age_months=1.0)
        result = NODDIAssumptionFlagger(
            infant_threshold_months=18, expected_d_par=1.5
        ).apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "OK:custom_d_par_matches_expected"

    def test_unexpected_d_par(self):
        df = make_df(noddi_d_par=2.1, session_age_months=12.0)
        result = NODDIAssumptionFlagger(
            infant_threshold_months=18, expected_d_par=1.7
        ).apply(df)
        flag = result["noddi_d_par_flag"].iloc[0]
        assert flag.startswith("WARN:unexpected_d_par")

    def test_missing_sidecar(self):
        df = make_df(noddi_d_par=float("nan"), session_age_months=6.0)
        result = NODDIAssumptionFlagger().apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "UNKNOWN:sidecar_missing"

    def test_no_noddi_column(self):
        df = make_df(session_age_months=6.0)
        result = NODDIAssumptionFlagger().apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "UNKNOWN:no_noddi_data"

    def test_multiple_rows_flagged_correctly(self):
        df = pd.DataFrame([
            {"subject": "sub-01", "session": "ses-1mo",  "bundle": "AF_left",
             "noddi_d_par": 1.7, "session_age_months": 1.0},
            {"subject": "sub-01", "session": "ses-36mo", "bundle": "AF_left",
             "noddi_d_par": 1.7, "session_age_months": 36.0},
        ])
        result = NODDIAssumptionFlagger(infant_threshold_months=18).apply(df)
        flags = result["noddi_d_par_flag"].tolist()
        assert flags[0] == "WARN:adult_default_d_par_in_infant"
        assert flags[1] == "INFO:adult_default_d_par"

    def test_threshold_boundary_inclusive(self):
        """Session exactly at the threshold should trigger the warning."""
        df = make_df(noddi_d_par=1.7, session_age_months=18.0)
        result = NODDIAssumptionFlagger(infant_threshold_months=18).apply(df)
        assert result["noddi_d_par_flag"].iloc[0] == "WARN:adult_default_d_par_in_infant"
