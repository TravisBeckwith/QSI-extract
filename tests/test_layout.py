"""Tests for qsi_extract.layout.bids_layout."""

from __future__ import annotations

import pytest

from qsi_extract.layout.bids_layout import BIDSLayout
import tests.conftest as conf


@pytest.fixture()
def layout(qsiprep_dir, qsirecon_dir):
    lay = BIDSLayout(qsiprep_dir=qsiprep_dir, qsirecon_dir=qsirecon_dir)
    lay.discover()
    return lay


def test_discover_subjects(layout):
    assert "sub-01" in layout.subjects
    assert "sub-02" in layout.subjects


def test_discover_sessions(layout):
    assert "ses-1mo" in layout.sessions
    assert "ses-6mo" in layout.sessions


def test_discover_recon_suffixes(layout):
    assert "NODDI" in layout.recon_suffixes


def test_version_detection_current(layout):
    """sub-01/ses-1mo should be detected as current (≥1.0) convention."""
    version = layout.qsiprep_version_map.get(("sub-01", "ses-1mo"))
    assert version == "current", f"Expected 'current', got {version!r}"


def test_iter_bundle_scalars_returns_files(layout):
    results = list(layout.iter_bundle_scalars())
    assert len(results) > 0
    for subject, session, path, source_type in results:
        assert subject.startswith("sub-")
        assert path.exists(), f"Path does not exist: {path}"
        assert source_type in ("bundle_means", "scalarstats", "tractometry")


def test_iter_bundle_scalars_respects_filter(qsiprep_dir, qsirecon_dir):
    lay = BIDSLayout(
        qsiprep_dir=qsiprep_dir,
        qsirecon_dir=qsirecon_dir,
        subjects=["01"],
    )
    lay.discover()
    results = list(lay.iter_bundle_scalars())
    subjects_found = {r[0] for r in results}
    assert subjects_found == {"sub-01"}, f"Unexpected subjects: {subjects_found}"


def test_iter_dwimap_jsons(layout):
    results = list(layout.iter_dwimap_jsons())
    assert len(results) > 0
    for subject, session, paths in results:
        assert isinstance(paths, list)
        assert all(p.exists() for p in paths)


def test_iter_qc_files(layout):
    results = list(layout.iter_qc_files())
    assert len(results) > 0
    for subject, session, qc_path, confounds_path in results:
        # At least one should be non-None for present sessions
        if session != "ses-6mo" or subject != "sub-02":
            assert qc_path is not None or confounds_path is not None


def test_missing_session_gap(layout):
    """sub-02 ses-6mo was not created — it should either be absent from
    iter results or yield None paths."""
    qc_results = {(r[0], r[1]): r[2] for r in layout.iter_qc_files()}
    # sub-02 ses-6mo was not built, so either it's absent or qc_path is None
    key = ("sub-02", "ses-6mo")
    if key in qc_results:
        assert qc_results[key] is None


def test_requires_discover():
    """Calling iter before discover should raise RuntimeError."""
    from pathlib import Path
    lay = BIDSLayout(qsiprep_dir=Path("/tmp"), qsirecon_dir=Path("/tmp"))
    with pytest.raises(RuntimeError, match="discover"):
        list(lay.iter_bundle_scalars())
