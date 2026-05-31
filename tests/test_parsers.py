"""Tests for qsi_extract.parsers.*"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from qsi_extract.parsers.bundle_means import BundleMeansParser, _normalise_scalar_name
from qsi_extract.parsers.tractometry import TractometryParser
from qsi_extract.parsers.dwimap_json import DwimapJsonParser
from qsi_extract.parsers.qc import QCParser


# ===========================================================================
# BundleMeansParser
# ===========================================================================

@pytest.fixture()
def bundle_means_tsv(tmp_path) -> Path:
    """Minimal bundle_means.tsv in the expected format."""
    df = pd.DataFrame([
        {"bundle_name": "AF_left",  "mean_fa": 0.38, "std_fa": 0.04, "mean_icvf": 0.42},
        {"bundle_name": "AF_right", "mean_fa": 0.40, "std_fa": 0.03, "mean_icvf": 0.44},
        {"bundle_name": "CST_left", "mean_fa": 0.51, "std_fa": 0.05, "mean_icvf": 0.55},
    ])
    path = tmp_path / "sub-01_ses-1mo_space-ACPC_bundle_means.tsv"
    df.to_csv(path, sep="\t", index=False)
    return path


@pytest.fixture()
def scalarstats_csv(tmp_path) -> Path:
    """Minimal DSI Studio scalarstats.csv format."""
    df = pd.DataFrame([
        {"tractname": "AF_left",  "dti_fa": 0.38, "gfa": 0.55, "mean_length": 85.2},
        {"tractname": "CST_left", "dti_fa": 0.51, "gfa": 0.60, "mean_length": 120.0},
    ])
    path = tmp_path / "sub-01_ses-1mo_bundles-DSIStudio_scalarstats.csv"
    df.to_csv(path, sep=",", index=False)
    return path


class TestBundleMeansParser:
    def test_parse_returns_records(self, bundle_means_tsv):
        records = BundleMeansParser(bundle_means_tsv, "sub-01", "ses-1mo").parse()
        assert len(records) > 0

    def test_subject_session_propagated(self, bundle_means_tsv):
        records = BundleMeansParser(bundle_means_tsv, "sub-01", "ses-1mo").parse()
        assert all(r["subject"] == "sub-01" for r in records)
        assert all(r["session"] == "ses-1mo" for r in records)

    def test_bundle_names_normalised(self, bundle_means_tsv):
        records = BundleMeansParser(bundle_means_tsv, "sub-01", "ses-1mo").parse()
        bundles = {r["bundle"] for r in records}
        assert "af_left" in bundles

    def test_scalar_names_canonical(self, bundle_means_tsv):
        records = BundleMeansParser(bundle_means_tsv, "sub-01", "ses-1mo").parse()
        scalars = {r["scalar"] for r in records}
        assert "fa_mean" in scalars
        assert "icvf_mean" in scalars

    def test_source_type_inferred(self, bundle_means_tsv):
        records = BundleMeansParser(bundle_means_tsv, "sub-01", "ses-1mo").parse()
        assert all(r["bundle_source"] == "bundle_means" for r in records)

    def test_scalarstats_csv(self, scalarstats_csv):
        records = BundleMeansParser(scalarstats_csv, "sub-01", "ses-1mo",
                                    source_type="scalarstats").parse()
        assert len(records) > 0
        scalars = {r["scalar"] for r in records}
        assert "fa_mean" in scalars  # dti_fa → fa_mean via map

    def test_empty_file_returns_empty(self, tmp_path):
        path = tmp_path / "empty_bundle_means.tsv"
        path.write_text("bundle_name\n")
        records = BundleMeansParser(path, "sub-01", "ses-1mo").parse()
        assert records == []

    def test_non_numeric_cells_skipped(self, tmp_path):
        df = pd.DataFrame([{"bundle_name": "AF_left", "mean_fa": "n/a", "mean_md": 0.0007}])
        path = tmp_path / "bundle_means.tsv"
        df.to_csv(path, sep="\t", index=False)
        records = BundleMeansParser(path, "sub-01", "ses-1mo").parse()
        scalars = {r["scalar"] for r in records}
        assert "fa_mean" not in scalars  # skipped
        assert "md_mean" in scalars


class TestScalarNameNormalisation:
    def test_mean_prefix(self):
        assert _normalise_scalar_name("mean_fa", "bundle_means") == "fa_mean"

    def test_std_prefix(self):
        assert _normalise_scalar_name("std_fa", "bundle_means") == "fa_std"

    def test_dti_fa(self):
        assert _normalise_scalar_name("dti_fa", "scalarstats") == "fa_mean"

    def test_unknown_passthrough(self):
        result = _normalise_scalar_name("exotic_metric", "bundle_means")
        assert result == "exotic_metric"


# ===========================================================================
# TractometryParser
# ===========================================================================

@pytest.fixture()
def tractometry_wide_csv(tmp_path) -> Path:
    """Wide along-tract format: rows=nodes, columns=bundles."""
    import numpy as np
    data = {"AF_left": list(np.linspace(0.3, 0.45, 100)),
            "AF_right": list(np.linspace(0.35, 0.48, 100)),
            "CST_left": list(np.linspace(0.4, 0.55, 100))}
    df = pd.DataFrame(data)
    path = tmp_path / "sub-01_ses-1mo_tractometry_FA.csv"
    df.to_csv(path, index=True)
    return path


class TestTractometryParser:
    def test_parse_wide_format(self, tractometry_wide_csv):
        records = TractometryParser(tractometry_wide_csv, "sub-01", "ses-1mo", scalar_name="fa").parse()
        assert len(records) > 0
        # Should have mean and std for each bundle
        scalars = {r["scalar"] for r in records}
        assert "fa_mean" in scalars
        assert "fa_std" in scalars

    def test_bundle_names_in_records(self, tractometry_wide_csv):
        records = TractometryParser(tractometry_wide_csv, "sub-01", "ses-1mo", scalar_name="fa").parse()
        bundles = {r["bundle"] for r in records}
        assert "af_left" in bundles

    def test_scalar_name_inferred_from_filename(self, tmp_path):
        df = pd.DataFrame({"AF_left": [0.38] * 10, "CST_left": [0.50] * 10})
        path = tmp_path / "Tractometry_MD.csv"
        df.to_csv(path, index=False)
        records = TractometryParser(path, "sub-01", "ses-1mo").parse()
        scalars = {r["scalar"] for r in records}
        assert "md_mean" in scalars


# ===========================================================================
# DwimapJsonParser
# ===========================================================================

@pytest.fixture()
def noddi_json_paths(tmp_path) -> list[Path]:
    paths = []
    for param in ("icvf", "isovf", "od"):
        meta = {"d_par": 1.7, "d_iso": 3.0, "Model": "noddi"}
        p = tmp_path / f"sub-01_ses-1mo_model-noddi_param-{param}_dwimap.json"
        p.write_text(json.dumps(meta))
        paths.append(p)
    # Add a modulated variant
    mod = tmp_path / "sub-01_ses-1mo_model-noddi_desc-modulated_param-icvf_dwimap.json"
    mod.write_text(json.dumps({"d_par": 1.7}))
    paths.append(mod)
    return paths


class TestDwimapJsonParser:
    def test_extracts_d_par(self, noddi_json_paths):
        records = DwimapJsonParser(noddi_json_paths, "sub-01", "ses-1mo").parse()
        assert len(records) == 1
        assert records[0]["noddi_d_par"] == pytest.approx(1.7)

    def test_extracts_d_iso(self, noddi_json_paths):
        records = DwimapJsonParser(noddi_json_paths, "sub-01", "ses-1mo").parse()
        assert records[0]["noddi_d_iso"] == pytest.approx(3.0)

    def test_modulated_present_flag(self, noddi_json_paths):
        records = DwimapJsonParser(noddi_json_paths, "sub-01", "ses-1mo").parse()
        assert records[0]["noddi_modulated_present"] is True

    def test_modulated_absent(self, tmp_path):
        p = tmp_path / "sub-01_ses-1mo_model-noddi_param-icvf_dwimap.json"
        p.write_text(json.dumps({"d_par": 1.7}))
        records = DwimapJsonParser([p], "sub-01", "ses-1mo").parse()
        assert records[0]["noddi_modulated_present"] is False

    def test_empty_paths_returns_empty(self):
        records = DwimapJsonParser([], "sub-01", "ses-1mo").parse()
        assert records == []

    def test_nan_when_key_absent(self, tmp_path):
        p = tmp_path / "sub-01_ses-1mo_model-noddi_param-icvf_dwimap.json"
        p.write_text(json.dumps({"Description": "no d_par here"}))
        records = DwimapJsonParser([p], "sub-01", "ses-1mo").parse()
        import math
        assert math.isnan(records[0]["noddi_d_par"])


# ===========================================================================
# QCParser
# ===========================================================================

@pytest.fixture()
def image_qc_tsv(tmp_path) -> Path:
    df = pd.DataFrame([{
        "mean_fd": 0.35,
        "max_fd": 1.1,
        "t1_neighbor_corr": 0.87,
        "t1_num_bad_slices": 2,
        "max_translation": 1.2,
        "t1_dice_distance": 0.03,
    }])
    path = tmp_path / "sub-01_ses-1mo_desc-image_qc.tsv"
    df.to_csv(path, sep="\t", index=False)
    return path


@pytest.fixture()
def confounds_tsv(tmp_path) -> Path:
    df = pd.DataFrame({"framewise_displacement": [0.2] * 90 + [0.8] * 9})
    path = tmp_path / "sub-01_ses-1mo_desc-confounds_timeseries.tsv"
    df.to_csv(path, sep="\t", index=False)
    return path


class TestQCParser:
    def test_parse_image_qc(self, image_qc_tsv):
        records = QCParser(image_qc_tsv, None, None, "sub-01", "ses-1mo").parse()
        assert len(records) == 1
        assert records[0]["qc_mean_fd"] == pytest.approx(0.35)
        assert records[0]["qc_ndc"] == pytest.approx(0.87)

    def test_parse_confounds_censoring(self, confounds_tsv):
        records = QCParser(None, confounds_tsv, None, "sub-01", "ses-1mo",
                           fd_threshold=0.5).parse()
        assert records[0]["qc_n_volumes"] == 99
        assert records[0]["qc_n_censored"] == 9
        assert records[0]["qc_pct_censored"] == pytest.approx(9 / 99)

    def test_both_sources(self, image_qc_tsv, confounds_tsv):
        records = QCParser(image_qc_tsv, confounds_tsv, None, "sub-01", "ses-1mo").parse()
        assert records[0]["qc_mean_fd"] == pytest.approx(0.35)
        assert records[0]["qc_n_censored"] == 9

    def test_none_paths_returns_empty(self):
        records = QCParser(None, None, None, "sub-01", "ses-1mo").parse()
        assert records == []
