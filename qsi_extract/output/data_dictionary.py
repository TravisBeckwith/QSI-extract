"""
qsi_extract.output.data_dictionary
=====================================

Auto-generate a data dictionary CSV describing every column in the output
table.

Known columns have hardcoded, authoritative descriptions.  Unknown columns
(e.g. novel scalars or MRIQC IQMs) are documented with a generic template
that records the column name, inferred dtype, and source prefix.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Hardcoded entries for all known columns
# ---------------------------------------------------------------------------

_KNOWN_COLUMNS: dict[str, dict] = {
    "subject": {
        "description": "BIDS subject label (e.g. sub-01)",
        "units": "",
        "model": "",
        "source_file_pattern": "BIDS directory structure",
        "notes": "",
    },
    "session": {
        "description": "BIDS session label (e.g. ses-1mo), or _no_session if no session layer",
        "units": "",
        "model": "",
        "source_file_pattern": "BIDS directory structure",
        "notes": "",
    },
    "session_age_months": {
        "description": "Subject age in months at this session, from <subject>_sessions.tsv",
        "units": "months",
        "model": "",
        "source_file_pattern": "sub-<label>_sessions.tsv",
        "notes": "NaN if sessions TSV absent or age column not found",
    },
    "bundle": {
        "description": "White matter bundle name (normalised: lowercase, underscores)",
        "units": "",
        "model": "",
        "source_file_pattern": "",
        "notes": "72 TractSeg bundles or DSI Studio autotrack bundles depending on workflow",
    },
    "scalar": {
        "description": "Scalar metric name (e.g. fa_mean, icvf_std)",
        "units": "",
        "model": "",
        "source_file_pattern": "",
        "notes": "Canonical names: fa_mean, md_mean, ad_mean, rd_mean, icvf_mean, isovf_mean, od_mean",
    },
    "value": {
        "description": "Scalar metric value for this subject/session/bundle/scalar combination",
        "units": "varies (FA: unitless 0-1; MD/AD/RD: mm²/s; ICVF/ISOVF/OD: unitless 0-1)",
        "model": "",
        "source_file_pattern": "",
        "notes": "NaN if scalar was not found for this combination (see scalar_present)",
    },
    "scalar_present": {
        "description": "Whether a scalar value was found for this subject/session/bundle/scalar",
        "units": "boolean",
        "model": "",
        "source_file_pattern": "",
        "notes": "False indicates a gap in the longitudinal data",
    },
    "recon_suffix": {
        "description": "QSIRecon workflow suffix that produced this scalar (e.g. NODDI, DTI)",
        "units": "",
        "model": "",
        "source_file_pattern": "qsirecon/derivatives/qsirecon-<suffix>/",
        "notes": "",
    },
    "bundle_source": {
        "description": "File type the bundle scalar was read from",
        "units": "",
        "model": "",
        "source_file_pattern": "",
        "notes": "One of: bundle_means, scalarstats, tractometry",
    },
    "noddi_d_par": {
        "description": "Intrinsic parallel diffusivity used for NODDI fitting (d_par)",
        "units": "µm²/ms",
        "model": "noddi",
        "source_file_pattern": "*_model-noddi_param-icvf_dwimap.json",
        "notes": "Default adult value is 1.7 µm²/ms; biased for infant tissue",
    },
    "noddi_d_par_flag": {
        "description": "Audit flag for the NODDI intrinsic diffusivity assumption",
        "units": "",
        "model": "noddi",
        "source_file_pattern": "*_model-noddi_param-icvf_dwimap.json",
        "notes": (
            "Values: OK:custom_d_par_matches_expected, INFO:adult_default_d_par, "
            "WARN:adult_default_d_par_in_infant, WARN:unexpected_d_par, "
            "UNKNOWN:sidecar_missing"
        ),
    },
    "noddi_d_iso": {
        "description": "Isotropic (free-water) diffusivity used for NODDI fitting",
        "units": "µm²/ms",
        "model": "noddi",
        "source_file_pattern": "*_model-noddi_param-isovf_dwimap.json",
        "notes": "Typically fixed at 3.0 µm²/ms",
    },
    "noddi_modulated_present": {
        "description": "Whether tissue-fraction modulated NODDI maps were found (Parker 2021)",
        "units": "boolean",
        "model": "noddi",
        "source_file_pattern": "*_model-noddi_desc-modulated_param-icvf_dwimap.json",
        "notes": "Requires QSIRecon >= 1.1.0; recommended for infant data",
    },
    "noddi_sidecar_count": {
        "description": "Number of NODDI dwimap JSON sidecars found for this session",
        "units": "count",
        "model": "noddi",
        "source_file_pattern": "*_model-noddi_*_dwimap.json",
        "notes": "",
    },
    "dti_fitting_method": {
        "description": "Tensor fitting method used (e.g. WLS, OLS)",
        "units": "",
        "model": "tensor",
        "source_file_pattern": "*_model-tensor_param-fa_dwimap.json",
        "notes": "",
    },
    "qc_mean_fd": {
        "description": "Mean framewise displacement across the DWI scan",
        "units": "mm",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_max_fd": {
        "description": "Maximum framewise displacement across the DWI scan",
        "units": "mm",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_ndc": {
        "description": "Neighboring DWI correlation (NDC) of preprocessed data — quality metric",
        "units": "unitless (0-1; higher is better)",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "Column t1_neighbor_corr in QSIPrep >= 1.0",
    },
    "qc_ndc_raw": {
        "description": "Neighboring DWI correlation (NDC) of raw (pre-preprocessing) data",
        "units": "unitless (0-1)",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_num_bad_slices": {
        "description": "Number of bad slices detected by DSI Studio in preprocessed data",
        "units": "count",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_num_bad_slices_raw": {
        "description": "Number of bad slices in raw data",
        "units": "count",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_max_translation": {
        "description": "Maximum absolute translation across the scan",
        "units": "mm",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_max_rotation": {
        "description": "Maximum absolute rotation across the scan",
        "units": "radians",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_t1_dice_distance": {
        "description": "Dice distance between anatomical and DWI brain masks (lower is better)",
        "units": "unitless (0-1)",
        "model": "",
        "source_file_pattern": "*_desc-image_qc.tsv",
        "notes": "",
    },
    "qc_n_volumes": {
        "description": "Total number of DWI volumes in the scan",
        "units": "count",
        "model": "",
        "source_file_pattern": "*_desc-confounds_timeseries.tsv",
        "notes": "",
    },
    "qc_n_censored": {
        "description": "Number of volumes with framewise displacement above the threshold",
        "units": "count",
        "model": "",
        "source_file_pattern": "*_desc-confounds_timeseries.tsv",
        "notes": "Threshold is qc_fd_threshold_used",
    },
    "qc_pct_censored": {
        "description": "Fraction of volumes censored (qc_n_censored / qc_n_volumes)",
        "units": "proportion (0-1)",
        "model": "",
        "source_file_pattern": "*_desc-confounds_timeseries.tsv",
        "notes": "",
    },
    "qc_fd_threshold_used": {
        "description": "Framewise displacement threshold used for censoring computation",
        "units": "mm",
        "model": "",
        "source_file_pattern": "",
        "notes": "Set by --fd-censoring-threshold (default: 0.5 mm)",
    },
    "qsiprep_version": {
        "description": "QSIPrep version string",
        "units": "",
        "model": "",
        "source_file_pattern": "qsiprep/dataset_description.json",
        "notes": "",
    },
    "qsirecon_version": {
        "description": "QSIRecon version string",
        "units": "",
        "model": "",
        "source_file_pattern": "qsirecon/derivatives/qsirecon-*/dataset_description.json",
        "notes": "",
    },
    "scalar_raw": {
        "description": "Original column name in the source file before normalisation",
        "units": "",
        "model": "",
        "source_file_pattern": "",
        "notes": "Kept for traceability; use 'scalar' for analysis",
    },
    "is_shape_stat": {
        "description": "Whether this scalar is a tractogram shape statistic rather than a diffusion metric",
        "units": "boolean",
        "model": "",
        "source_file_pattern": "*_scalarstats.csv",
        "notes": "Shape stats: mean_length, volume, span, curl, endpoint_radius",
    },
}


class DataDictionaryBuilder:
    """Build a data dictionary DataFrame from the primary output table.

    Parameters
    ----------
    df:
        The primary longitudinal table.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

    def build(self) -> pd.DataFrame:
        """Return a DataFrame with one row per column in *self.df*."""
        rows = []
        for col in self.df.columns:
            if col in _KNOWN_COLUMNS:
                entry = _KNOWN_COLUMNS[col].copy()
            else:
                # Auto-generate entry for unknown columns
                entry = self._auto_entry(col)
            entry["column_name"] = col
            rows.append(entry)

        dd = pd.DataFrame(rows, columns=[
            "column_name", "description", "units", "model",
            "source_file_pattern", "notes",
        ])
        return dd

    def _auto_entry(self, col: str) -> dict:
        """Generate a generic entry for an undocumented column."""
        # Infer source from prefix
        if col.startswith("mriqc_"):
            source = "mriqc/dwi_group.tsv"
            desc = f"MRIQC IQM: {col.removeprefix('mriqc_')}"
        elif col.startswith("qc_"):
            source = "*_desc-image_qc.tsv or *_desc-confounds_timeseries.tsv"
            desc = f"QSIPrep QC metric: {col.removeprefix('qc_')}"
        elif col.startswith("noddi_"):
            source = "*_model-noddi_*_dwimap.json"
            desc = f"NODDI model parameter: {col.removeprefix('noddi_')}"
        elif col.startswith("dti_"):
            source = "*_model-tensor_*_dwimap.json"
            desc = f"DTI model parameter: {col.removeprefix('dti_')}"
        else:
            source = ""
            desc = f"Auto-documented column: {col}"

        dtype_str = str(self.df[col].dtype)
        return {
            "description": desc,
            "units": "",
            "model": "",
            "source_file_pattern": source,
            "notes": f"Auto-generated entry. dtype={dtype_str}",
        }
