"""Tests for qsi_extract.cli argument parsing and config construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from qsi_extract.cli import build_parser
from qsi_extract.config import ExtractorConfig


class TestCLIParser:
    def test_required_args(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir",  str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir",   str(tmp_path / "out"),
        ])
        assert args.qsiprep_dir == tmp_path
        assert args.qsirecon_dir == tmp_path

    def test_missing_required_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parquet_flag(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir", str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "--parquet",
        ])
        assert args.write_parquet is True

    def test_no_qc_flag(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir", str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "--no-qc",
        ])
        assert args.no_qc is True

    def test_verbosity_count(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir", str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "-vv",
        ])
        assert args.verbose == 2

    def test_subjects_list(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir", str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "--subjects", "01", "02", "03",
        ])
        assert args.subjects == ["01", "02", "03"]

    def test_scalar_format_choices(self, tmp_path):
        parser = build_parser()
        args = parser.parse_args([
            "--qsiprep-dir", str(tmp_path),
            "--qsirecon-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "--scalar-format", "wide",
        ])
        assert args.scalar_format == "wide"

    def test_invalid_scalar_format_exits(self, tmp_path):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "--qsiprep-dir", str(tmp_path),
                "--qsirecon-dir", str(tmp_path),
                "--output-dir", str(tmp_path / "out"),
                "--scalar-format", "invalid",
            ])


class TestExtractorConfigValidation:
    def test_nonexistent_qsiprep_dir(self, tmp_path):
        config = ExtractorConfig(
            qsiprep_dir=tmp_path / "nonexistent",
            qsirecon_dir=tmp_path,
            output_dir=tmp_path / "out",
        )
        with pytest.raises(ValueError, match="qsiprep_dir"):
            config.validate()

    def test_parquet_without_pyarrow(self, tmp_path, monkeypatch):
        """write_parquet=True should raise ImportError if pyarrow is absent."""
        import sys
        monkeypatch.setitem(sys.modules, "pyarrow", None)
        config = ExtractorConfig(
            qsiprep_dir=tmp_path,
            qsirecon_dir=tmp_path,
            output_dir=tmp_path / "out",
            write_parquet=True,
        )
        with pytest.raises(ImportError, match="pyarrow"):
            config.validate()

    def test_serialisation_roundtrip(self, tmp_path):
        config = ExtractorConfig(
            qsiprep_dir=tmp_path,
            qsirecon_dir=tmp_path,
            output_dir=tmp_path / "out",
            noddi_infant_threshold_months=12.0,
        )
        json_path = tmp_path / "config.json"
        config.to_json(json_path)
        loaded = ExtractorConfig.from_json(json_path)
        assert loaded.noddi_infant_threshold_months == 12.0
        assert str(loaded.qsiprep_dir) == str(tmp_path)
