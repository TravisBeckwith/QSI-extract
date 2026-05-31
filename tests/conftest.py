"""
Shared pytest fixtures for qsi-extract tests.

Builds a minimal but realistic synthetic BIDS derivative tree at
``tests/fixtures/`` that mirrors the real QSIPrep/QSIRecon output
structure, covering both QSIPrep ≥1.0 (space-ACPC) file conventions and
the QSIRecon bundle_means + dwimap JSON layout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Root fixture directories (relative to this file)
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
QSIPREP_DIR = FIXTURE_DIR / "qsiprep"
QSIRECON_DIR = FIXTURE_DIR / "qsirecon"
MRIQC_DIR = FIXTURE_DIR / "mriqc"


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

SUBJECTS = ["sub-01", "sub-02"]
SESSIONS = ["ses-1mo", "ses-6mo"]  # sub-02 ses-6mo will be intentionally absent
BUNDLES = ["AF_left", "AF_right", "CST_left", "CST_right"]
SCALARS = {"fa": 0.38, "md": 0.00075, "icvf": 0.42, "isovf": 0.08, "od": 0.19}


@pytest.fixture(scope="session", autouse=True)
def build_fixtures(tmp_path_factory):
    """Build the synthetic BIDS fixture tree once per test session."""
    root = tmp_path_factory.mktemp("bids_fixtures")

    qsiprep = root / "qsiprep"
    qsirecon = root / "qsirecon"
    mriqc = root / "mriqc"

    _build_qsiprep(qsiprep)
    _build_qsirecon(qsirecon)
    _build_mriqc(mriqc)

    # Store paths on the module so fixtures can access them
    import tests.conftest as conf
    conf._TMP_QSIPREP = qsiprep
    conf._TMP_QSIRECON = qsirecon
    conf._TMP_MRIQC = mriqc

    return root


# These are set by build_fixtures at session startup
_TMP_QSIPREP: Path = None
_TMP_QSIRECON: Path = None
_TMP_MRIQC: Path = None


@pytest.fixture()
def qsiprep_dir():
    return _TMP_QSIPREP


@pytest.fixture()
def qsirecon_dir():
    return _TMP_QSIRECON


@pytest.fixture()
def mriqc_dir():
    return _TMP_MRIQC


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_qsiprep(root: Path) -> None:
    """Build synthetic QSIPrep ≥1.0 derivative tree."""
    _write_dataset_description(root, "QSIPrep", "1.1.2")

    for sub in SUBJECTS:
        for ses in SESSIONS:
            if sub == "sub-02" and ses == "ses-6mo":
                continue  # intentional gap

            dwi_dir = root / sub / ses / "dwi"
            dwi_dir.mkdir(parents=True, exist_ok=True)

            prefix = f"{sub}_{ses}_space-ACPC_desc-preproc"

            # image_qc.tsv (current format)
            qc = pd.DataFrame([{
                "mean_fd": 0.35 if ses == "ses-1mo" else 0.28,
                "max_fd": 1.1,
                "t1_neighbor_corr": 0.87,
                "raw_neighbor_corr": 0.82,
                "t1_num_bad_slices": 1,
                "raw_num_bad_slices": 3,
                "max_translation": 1.2,
                "max_rotation": 0.018,
                "t1_dice_distance": 0.03,
            }])
            qc.to_csv(dwi_dir / f"{prefix}_dwi_desc-image_qc.tsv", sep="\t", index=False)

            # confounds_timeseries.tsv
            n_vols = 99
            fd_vals = [0.2] * 90 + [0.8] * 9  # 9 volumes above 0.5mm
            confounds = pd.DataFrame({
                "framewise_displacement": fd_vals,
                "trans_x": [0.0] * n_vols,
                "trans_y": [0.0] * n_vols,
                "trans_z": [0.0] * n_vols,
            })
            confounds.to_csv(
                dwi_dir / f"{prefix}_dwi_desc-confounds_timeseries.tsv",
                sep="\t", index=False,
            )

    # sessions.tsv with age data
    for sub in SUBJECTS:
        base_age = 1 if sub == "sub-01" else 2
        tsv = pd.DataFrame({
            "session_id": SESSIONS,
            "age_months": [base_age, base_age + 5],
        })
        (root / sub).mkdir(parents=True, exist_ok=True)
        tsv.to_csv(root / sub / f"{sub}_sessions.tsv", sep="\t", index=False)


def _build_qsirecon(root: Path) -> None:
    """Build synthetic QSIRecon derivative tree with NODDI workflow."""
    recon_dir = root / "derivatives" / "qsirecon-NODDI"
    _write_dataset_description(recon_dir, "QSIRecon", "1.1.1")

    for sub in SUBJECTS:
        for ses in SESSIONS:
            if sub == "sub-02" and ses == "ses-6mo":
                continue

            dwi_dir = recon_dir / sub / ses / "dwi"
            dwi_dir.mkdir(parents=True, exist_ok=True)

            prefix = f"{sub}_{ses}_space-ACPC_desc-preproc"

            # bundle_means.tsv
            rows = []
            for bundle in BUNDLES:
                row = {"bundle_name": bundle}
                for scalar, base_val in SCALARS.items():
                    row[f"mean_{scalar}"] = round(base_val + 0.01 * hash(f"{sub}{ses}{bundle}{scalar}") % 10 * 0.01, 4)
                    row[f"std_{scalar}"] = round(0.02 + 0.001 * hash(f"std{bundle}{scalar}") % 10 * 0.01, 4)
                rows.append(row)
            pd.DataFrame(rows).to_csv(
                dwi_dir / f"{prefix}_bundle_means.tsv",
                sep="\t", index=False,
            )

            # NODDI dwimap JSON sidecars
            for param in ("icvf", "isovf", "od"):
                meta = {
                    "Description": f"NODDI {param} map",
                    "Model": "noddi",
                    "d_par": 1.7,  # adult default — will trigger WARN for infant sessions
                    "d_iso": 3.0,
                }
                json_path = dwi_dir / f"{prefix}_model-noddi_param-{param}_dwimap.json"
                json_path.write_text(json.dumps(meta, indent=2))

            # Modulated ICVF JSON (present — simulates QSIRecon ≥1.1)
            mod_meta = {"Description": "Modulated NODDI icvf", "Model": "noddi", "d_par": 1.7}
            (dwi_dir / f"{prefix}_model-noddi_desc-modulated_param-icvf_dwimap.json").write_text(
                json.dumps(mod_meta, indent=2)
            )


def _build_mriqc(root: Path) -> None:
    """Build synthetic MRIQC group TSV."""
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for sub in SUBJECTS:
        for ses in SESSIONS:
            if sub == "sub-02" and ses == "ses-6mo":
                continue
            rows.append({
                "subject_id": sub,
                "session_id": ses,
                "fd_mean": 0.32,
                "snr_wm": 18.5,
                "efc": 0.45,
            })
    pd.DataFrame(rows).to_csv(root / "dwi_group.tsv", sep="\t", index=False)


def _write_dataset_description(directory: Path, name: str, version: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    desc = {
        "Name": name,
        "BIDSVersion": "1.8.0",
        "GeneratedBy": [{"Name": name, "Version": version}],
    }
    (directory / "dataset_description.json").write_text(json.dumps(desc, indent=2))
