"""
qsi_extract.layout.file_patterns
=================================

Central registry of all file glob patterns and regex for QSIPrep and
QSIRecon outputs.

Design notes
------------
- Patterns are plain strings suitable for ``Path.glob()`` and
  ``Path.rglob()``.
- Two naming convention eras are tracked: QSIPrep <1.0 ("legacy") and
  ≥1.0 ("current").  The layout module checks both and records which was
  found so version info can be propagated into output metadata.
- ``BUNDLE_SCALAR_PRIORITY`` defines the probe order used by
  ``BIDSLayout.iter_bundle_scalars()`` when ``bundle_source="auto"``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# QSIPrep — preprocessed DWI
# ---------------------------------------------------------------------------

# Sidecar JSON with acquisition metadata (contains PhaseEncodingDirection,
# RepetitionTime, etc.)
QSIPREP_DWI_JSON = {
    "current": "*_space-ACPC_desc-preproc_dwi.json",
    "legacy":  "*_space-T1w_desc-preproc_dwi.json",
}

# Per-scan QC summary (NDC, FD summary, bad slices, voxel dimensions, …)
QSIPREP_IMAGE_QC = {
    "current": "*_desc-image_qc.tsv",   # QSIPrep ≥1.0
    "legacy":  "*_desc-ImageQC_dwi.csv",  # QSIPrep <1.0
}

# Per-volume confounds (framewise_displacement, trans_x/y/z, rot_x/y/z, …)
QSIPREP_CONFOUNDS = {
    "current": "*_desc-confounds_timeseries.tsv",
    "legacy":  "*_confounds.tsv",
}

# ---------------------------------------------------------------------------
# QSIRecon — bundle-level scalar tables
# ---------------------------------------------------------------------------

# Output of a custom ``bundle_map`` node (most informative; preferred)
#   Columns: bundle_name, mean_<scalar>, std_<scalar>, …
BUNDLE_MEANS_TSV = "*_bundle_means.tsv"

# DSI Studio autotrack / hbcd_scalar_maps workflow
#   Columns: dti_fa, gfa, qa, iso, mean_length, volume, …
SCALARSTATS_CSV = "*bundles-*_scalarstats.csv"

# TractSeg / Scilpy tractometry (along-tract node values; collapsed to means)
#   Either a single multi-bundle CSV or per-scalar files
TRACTOMETRY_CSV = "*_tractometry.csv"

# Priority order for bundle_source="auto"
BUNDLE_SCALAR_PRIORITY: list[tuple[str, str]] = [
    ("bundle_means",  BUNDLE_MEANS_TSV),
    ("scalarstats",   SCALARSTATS_CSV),
    ("tractometry",   TRACTOMETRY_CSV),
]

# ---------------------------------------------------------------------------
# QSIRecon — per-voxel scalar map JSON sidecars
# ---------------------------------------------------------------------------

# NODDI (AMICO) dwimap JSON sidecars — contain d_par, fitting parameters
NODDI_DWIMAP_JSON_PARAMS = [
    "icvf",      # NDI  — intracellular volume fraction
    "isovf",     # FWF  — isotropic volume fraction
    "od",        # ODI  — orientation dispersion index
]

# Tissue-fraction modulated variants (QSIRecon ≥1.1; desc-modulated)
NODDI_MODULATED_PARAMS = [
    "modulated-icvf",
    "modulated-od",
]

# Pattern template; format with param name
NODDI_DWIMAP_JSON_PATTERN = "*_model-noddi_param-{param}_dwimap.json"
NODDI_MODULATED_JSON_PATTERN = "*_model-noddi_desc-modulated_param-{param}_dwimap.json"

# DTI dwimap JSON sidecars
DTI_DWIMAP_JSON_PARAMS = ["fa", "md", "ad", "rd"]
DTI_DWIMAP_JSON_PATTERN = "*_model-tensor_param-{param}_dwimap.json"

# ---------------------------------------------------------------------------
# MRIQC — group-level QC
# ---------------------------------------------------------------------------

MRIQC_DWI_GROUP_TSV = "dwi_group.tsv"

# ---------------------------------------------------------------------------
# BIDS sessions file (age metadata)
# ---------------------------------------------------------------------------

# These live under the subject directory or at dataset root
SESSIONS_TSV_PATTERNS = [
    "sub-{subject}_sessions.tsv",  # <bids_root>/sub-<label>/sub-<label>_sessions.tsv
    "sessions.tsv",                # <bids_root>/sessions.tsv (non-standard but seen)
]

# ---------------------------------------------------------------------------
# QSIRecon derivatives sub-directory structure
# ---------------------------------------------------------------------------

# Each recon workflow writes to its own subdataset:
#   qsirecon/derivatives/qsirecon-<SUFFIX>/sub-.../ses-.../dwi/
QSIRECON_DERIVATIVES_GLOB = "derivatives/qsirecon-*/sub-*/dwi/"
QSIRECON_DERIVATIVES_GLOB_WITH_SESSION = "derivatives/qsirecon-*/sub-*/ses-*/dwi/"

# dataset_description.json — contains GeneratedBy with version info
DATASET_DESCRIPTION = "dataset_description.json"
