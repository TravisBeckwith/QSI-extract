# qsi-extract

**A standalone Python tool for extracting and collating diffusion MRI scalar outputs from QSIPrep and QSIRecon into tidy, longitudinal tabular datasets.**

`qsi-extract` traverses BIDS derivative trees produced by [QSIPrep](https://qsiprep.readthedocs.io) and [QSIRecon](https://qsirecon.readthedocs.io), parses per-bundle and per-ROI scalar files (NODDI, DTI, and more), audits model fitting assumptions, propagates QC flags, and writes clean longitudinal tables ready for statistical analysis.

Designed for infant and pediatric longitudinal studies, but general-purpose for any BIDS-organized diffusion pipeline.

---

## Contents

- [Motivation](#motivation)
- [Features](#features)
- [Supported Inputs](#supported-inputs)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Command-Line Interface](#command-line-interface)
  - [Python API](#python-api)
- [Output Schema](#output-schema)
  - [Primary table](#primary-table)
  - [Data dictionary](#data-dictionary)
  - [Run log](#run-log)
- [NODDI Assumption Auditing](#noddi-assumption-auditing)
- [QC Flag Propagation](#qc-flag-propagation)
- [Handling Missing Data](#handling-missing-data)
- [Supported File Patterns](#supported-file-patterns)
- [Configuration](#configuration)
- [Package Architecture](#package-architecture)
- [Development](#development)
- [Known Limitations](#known-limitations)
- [Citation](#citation)
- [License](#license)

---

## Motivation

After running QSIPrep → QSIRecon, scalar outputs are scattered across a deeply nested derivative tree: per-model subdatasets, per-subject directories, per-session subdirectories, with QC metrics in yet another location. Collating these into a single analysis-ready table requires understanding several evolving file naming conventions, handling missing sessions gracefully in longitudinal cohorts, auditing model assumptions that vary across subjects, and joining QC metadata before any statistical work can begin.

`qsi-extract` automates all of that. It is intentionally a **leaf tool** — it reads derivatives and writes tables, with no dependency on neuroimaging libraries and no coupling to upstream or downstream pipelines.

---

## Features

- **BIDS-aware traversal** of QSIPrep and QSIRecon derivative trees using pure `pathlib` — no pybids dependency
- **Version-transparent** — handles QSIPrep <1.0 (`space-T1w`, `desc-ImageQC_dwi.csv`) and ≥1.0 (`space-ACPC`, `desc-image_qc.tsv`) naming conventions side-by-side
- **Multi-format scalar ingestion**: `bundle_means.tsv` (custom `bundle_map` node), `*_scalarstats.csv` (DSI Studio autotrack), TractSeg/Scilpy `Tractometry.csv`, per-voxel `*_dwimap.json` sidecars
- **NODDI assumption auditing**: extracts `d_par` (intrinsic diffusivity) from JSON sidecars, flags sessions using the adult default (1.7 µm²/ms) in infant data, and records tissue-fraction modulation status (Parker 2021)
- **QC flag propagation**: joins `desc-image_qc.tsv` (NDC, mean/max FD, bad slices, dice distances), per-volume confounds (censoring counts), and optional MRIQC group TSVs into every output row
- **Longitudinal gap handling**: outer-joins over the full subject × session × bundle grid; missing cells become `NaN` with companion `_present` boolean columns
- **Structured warning log**: per-subject summary of missing files, unexpected column sets, and assumption violations — written alongside the output table
- **Auto-generated data dictionary**: one row per output column with description, units, source file pattern, model, and notes
- **Output formats**: CSV (always) and optionally Parquet (requires `pyarrow`)

---

## Supported Inputs

### QSIPrep outputs (preprocessing derivatives)

| File | Versions | Content |
|---|---|---|
| `*_space-ACPC_desc-preproc_dwi.json` | ≥1.0 | DWI acquisition metadata |
| `*_space-T1w_desc-preproc_dwi.json` | <1.0 | DWI acquisition metadata (legacy) |
| `*_desc-image_qc.tsv` | ≥1.0 | Per-scan QC: NDC, FD summary, bad slices, dice distances |
| `*_desc-ImageQC_dwi.csv` | <1.0 | Per-scan QC (legacy CSV format) |
| `*_desc-confounds_timeseries.tsv` | ≥1.0 | Per-volume FD, motion params for censoring counts |

### QSIRecon outputs (reconstruction derivatives)

**Bundle-level scalar tables — primary targets:**

| File | Workflow | Content |
|---|---|---|
| `*_bundle_means.tsv` | Custom `bundle_map` node | Mean ± SD of all scalars per bundle |
| `*bundles-*_scalarstats.csv` | `dsi_studio_autotrack`, `hbcd_scalar_maps` | Scalar stats + shape metrics per bundle |
| `*_tractometry.csv` | TractSeg / Scilpy | Along-tract node values (collapsed to bundle means) |

**Per-voxel scalar map sidecars — for model auditing:**

| File pattern | Model | Key parameters extracted |
|---|---|---|
| `*_model-noddi_param-icvf_dwimap.json` | AMICO NODDI | `d_par`, fitting parameters |
| `*_model-noddi_param-isovf_dwimap.json` | AMICO NODDI | `d_iso` |
| `*_model-noddi_desc-modulated_param-icvf_dwimap.json` | AMICO NODDI ≥1.1 | Modulated map presence flag |
| `*_model-tensor_param-fa_dwimap.json` | Dipy/TORTOISE DTI | Tensor fitting parameters |

### Optional QC inputs

| File | Tool | Content |
|---|---|---|
| `mriqc/dwi_group.tsv` | MRIQC | Group-level IQMs (fd_mean, snr_*, efc, …) |

### NODDI scalar names across workflows

| Canonical name | QSIRecon `param` entity | Description |
|---|---|---|
| NDI | `icvf` | Neurite density index (intracellular volume fraction) |
| ODI | `od` | Orientation dispersion index |
| FWF | `isovf` | Free water fraction (isotropic volume fraction) |
| NDI-mod | `modulated-icvf` | Tissue-fraction modulated NDI (Parker 2021; QSIRecon ≥1.1) |
| ODI-mod | `modulated-od` | Tissue-fraction modulated ODI (Parker 2021; QSIRecon ≥1.1) |

### DTI scalar names

| Canonical name | QSIRecon `param` entity | Description |
|---|---|---|
| FA | `fa` | Fractional anisotropy |
| MD | `md` | Mean diffusivity |
| AD | `ad` | Axial diffusivity (λ₁) |
| RD | `rd` | Radial diffusivity ((λ₂+λ₃)/2) |

---

## Installation

### From PyPI (once published)

### From source

```bash
git clone https://github.com/TravisBeckwith/qsi-extract.git
cd qsi-extract
pip install -e ".[dev]"
```

### Optional dependency: Parquet output

```bash
pip install qsi-extract[parquet]
# or: pip install pyarrow
```

### Requirements

- Python ≥ 3.9
- `pandas` ≥ 1.5
- `pyarrow` ≥ 10.0 *(optional, for Parquet output)*

No neuroimaging libraries required (`nibabel`, `nilearn`, `pybids` are not dependencies).

---

## Quick Start

```bash
# Minimal: extract everything found, write CSV
qsi-extract \
  --qsiprep-dir  /data/derivatives/qsiprep \
  --qsirecon-dir /data/derivatives/qsirecon \
  --output-dir   /data/derivatives/qsi_extract

# With MRIQC QC and Parquet output
qsi-extract \
  --qsiprep-dir  /data/derivatives/qsiprep \
  --qsirecon-dir /data/derivatives/qsirecon \
  --mriqc-dir    /data/derivatives/mriqc \
  --output-dir   /data/derivatives/qsi_extract \
  --parquet

# Infant study: flag adult-default d_par in sessions under 18 months
qsi-extract \
  --qsiprep-dir  /data/derivatives/qsiprep \
  --qsirecon-dir /data/derivatives/qsirecon \
  --output-dir   /data/derivatives/qsi_extract \
  --noddi-infant-threshold-months 18
```

This produces:

```
/data/derivatives/qsi_extract/
  scalars_longitudinal.csv          # main output table
  scalars_longitudinal.parquet      # (if --parquet)
  data_dictionary.csv               # column descriptions
  run_log.tsv                       # per-subject warnings and file inventory
  config_used.json                  # full configuration snapshot
```

---

## Usage

### Command-Line Interface

```
usage: qsi-extract [-h] --qsiprep-dir PATH --qsirecon-dir PATH --output-dir PATH
                   [--mriqc-dir PATH]
                   [--subjects SUBJECT [SUBJECT ...]]
                   [--sessions SESSION [SESSION ...]]
                   [--recon-suffixes SUFFIX [SUFFIX ...]]
                   [--bundle-source {bundle_means,scalarstats,tractometry,auto}]
                   [--scalar-format {long,wide}]
                   [--noddi-infant-threshold-months N]
                   [--noddi-expected-d-par VALUE]
                   [--missing-session-policy {warn,error,ignore}]
                   [--parquet]
                   [--no-qc]
                   [--no-data-dictionary]
                   [--config PATH]
                   [-v]
```

#### Required arguments

| Argument | Description |
|---|---|
| `--qsiprep-dir PATH` | Root of the QSIPrep derivatives dataset (`qsiprep/` folder) |
| `--qsirecon-dir PATH` | Root of the QSIRecon derivatives dataset (`qsirecon/` folder) |
| `--output-dir PATH` | Directory to write all outputs (created if absent) |

#### Optional arguments

| Argument | Default | Description |
|---|---|---|
| `--mriqc-dir PATH` | — | Path to MRIQC derivatives; enables MRIQC QC column propagation |
| `--subjects` | all found | Space-delimited list of subject labels (without `sub-` prefix) |
| `--sessions` | all found | Space-delimited list of session labels (without `ses-` prefix) |
| `--recon-suffixes` | all found | Limit to specific QSIRecon workflow suffixes (e.g. `NODDI DTI`) |
| `--bundle-source` | `auto` | Which bundle scalar file type to prefer; `auto` checks in priority order |
| `--scalar-format` | `long` | `long`: one row per sub×ses×bundle×scalar; `wide`: one row per sub×ses×bundle |
| `--noddi-infant-threshold-months` | `18` | Sessions with age ≤ this value trigger adult-d_par warning |
| `--noddi-expected-d-par` | `1.7` | Expected (non-default) d_par value for your cohort; deviations are flagged |
| `--missing-session-policy` | `warn` | How to handle absent sessions: `warn` (log and continue), `error` (abort), `ignore` |
| `--parquet` | off | Write Parquet in addition to CSV |
| `--no-qc` | off | Skip QC file ingestion entirely |
| `--no-data-dictionary` | off | Skip data dictionary generation |
| `--config PATH` | — | JSON config file; CLI arguments override config file values |
| `-v` / `--verbose` | — | Increase logging verbosity (repeat for DEBUG: `-vv`) |

### Python API

```python
from qsi_extract import Extractor
from qsi_extract.config import ExtractorConfig

config = ExtractorConfig(
    qsiprep_dir="/data/derivatives/qsiprep",
    qsirecon_dir="/data/derivatives/qsirecon",
    output_dir="/data/derivatives/qsi_extract",
    mriqc_dir="/data/derivatives/mriqc",
    noddi_infant_threshold_months=18,
    write_parquet=True,
)

extractor = Extractor(config)
df = extractor.run()          # returns the primary DataFrame
print(df.head())
```

Lower-level access for custom pipelines:

```python
from qsi_extract.layout import BIDSLayout
from qsi_extract.parsers import BundleMeansParser, QCParser, DwimapJsonParser
from qsi_extract.collators import LongitudinalCollator

layout = BIDSLayout(qsiprep_dir=..., qsirecon_dir=...)

for subject, session, path in layout.iter_bundle_scalars():
    records = BundleMeansParser(path).parse()   # list of dicts
    ...

collator = LongitudinalCollator()
df = collator.collate(records)
```

---

## Output Schema

### Primary table

The default output format is **long**: one row per subject × session × bundle × scalar.

| Column | Type | Description |
|---|---|---|
| `subject` | str | Subject label (e.g. `sub-01`) |
| `session` | str | Session label (e.g. `ses-1mo`) |
| `session_age_months` | float | Age in months at session, if available from `sessions.tsv` |
| `bundle` | str | Bundle name (e.g. `AF_left`, `CST_right`) |
| `scalar` | str | Scalar name (e.g. `fa_mean`, `icvf_mean`, `od_std`) |
| `value` | float | Scalar value |
| `recon_suffix` | str | QSIRecon workflow suffix that produced this scalar |
| `bundle_source` | str | Which file type the bundle row came from |
| `scalar_present` | bool | Whether this scalar was found for this sub×ses×bundle |
| `noddi_d_par` | float | Intrinsic diffusivity used for NODDI fit (from JSON sidecar) |
| `noddi_d_par_flag` | str | Assumption audit flag (see [NODDI Assumption Auditing](#noddi-assumption-auditing)) |
| `noddi_modulated_present` | bool | Whether tissue-fraction modulated maps were found (QSIRecon ≥1.1) |
| `qc_mean_fd` | float | Mean framewise displacement for this scan |
| `qc_max_fd` | float | Maximum framewise displacement |
| `qc_ndc` | float | Neighboring DWI correlation (raw and preprocessed) |
| `qc_num_bad_slices` | int | Number of bad slices detected by DSI Studio |
| `qc_pct_censored` | float | Fraction of volumes with FD above threshold (from confounds TSV) |
| `qc_t1_dice_distance` | float | Anatomical / DWI brain mask overlap (Dice distance) |
| `qsiprep_version` | str | QSIPrep version string (from `dataset_description.json`) |
| `qsirecon_version` | str | QSIRecon version string |

**Wide format** (one row per sub×ses×bundle, `--scalar-format wide`) pivots scalar names into columns: `fa_mean`, `fa_std`, `icvf_mean`, `icvf_std`, etc., with the same QC and flag columns appended.

### Data dictionary

`data_dictionary.csv` — one row per output column:

| Column | Description |
|---|---|
| `column_name` | Column name in the primary table |
| `description` | Human-readable description |
| `units` | Physical units where applicable |
| `model` | Diffusion model (noddi, tensor, gqi, …) |
| `source_file_pattern` | Glob pattern of the file this column originates from |
| `notes` | Caveats, version dependencies, or audit notes |

### Run log

`run_log.tsv` — one row per subject × session:

| Column | Description |
|---|---|
| `subject` | Subject label |
| `session` | Session label |
| `status` | `ok`, `partial`, `missing` |
| `bundle_scalar_file` | Path to the bundle scalar file used, if found |
| `qc_file` | Path to the QC TSV used, if found |
| `confounds_file` | Path to the confounds TSV used, if found |
| `noddi_json_found` | Whether NODDI dwimap JSON sidecar was found |
| `warnings` | Pipe-delimited list of warning messages |

---

## NODDI Assumption Auditing

The NODDI model assumes a fixed intrinsic parallel diffusivity `d_par` = 1.7 µm²/ms, calibrated for adult white matter. This assumption is known to be biased for infant tissue, where diffusivities differ substantially during rapid myelination and axonal growth in the first years of life.

`qsi-extract` extracts `d_par` from the `*_model-noddi_param-icvf_dwimap.json` sidecar written by QSIRecon's AMICO interface and applies the following audit logic:

```
d_par == 1.7  AND  session_age_months <= noddi_infant_threshold_months
    → noddi_d_par_flag = "WARN:adult_default_d_par_in_infant"

d_par == 1.7  AND  session_age_months > noddi_infant_threshold_months
    → noddi_d_par_flag = "INFO:adult_default_d_par"

d_par != 1.7  AND  d_par == noddi_expected_d_par
    → noddi_d_par_flag = "OK:custom_d_par_matches_expected"

d_par != 1.7  AND  d_par != noddi_expected_d_par
    → noddi_d_par_flag = "WARN:unexpected_d_par"

JSON sidecar not found
    → noddi_d_par_flag = "UNKNOWN:sidecar_missing"
```

The `--noddi-expected-d-par` flag lets you set the cohort-appropriate value (if your AMICO runs used a custom value), so deviations from your protocol are caught rather than silently propagated.

The tissue-fraction modulated maps (Parker 2021) added in QSIRecon v1.1.0 are recommended for infant data because CSF partial-volume effects are especially pronounced in immature brains. The `noddi_modulated_present` column flags whether these maps were available, letting downstream analysts choose whether to use raw or modulated ICVF/ODI values.

---

## QC Flag Propagation

QC metrics are sourced from three locations and joined into every output row on subject × session:

**From `desc-image_qc.tsv` (QSIPrep ≥1.0) or `desc-ImageQC_dwi.csv` (<1.0):**
- `qc_mean_fd` — mean framewise displacement across the scan
- `qc_max_fd` — maximum framewise displacement
- `qc_ndc` — neighboring DWI correlation (quality of raw data)
- `qc_num_bad_slices` — DSI Studio bad-slice count
- `qc_max_translation`, `qc_max_rotation`
- `qc_t1_dice_distance` — brain mask overlap

**Computed from `desc-confounds_timeseries.tsv`:**
- `qc_n_volumes` — total volume count
- `qc_n_censored` — volumes with `framewise_displacement` > threshold (default 0.5 mm)
- `qc_pct_censored` — `n_censored / n_volumes`
- `qc_fd_threshold_used` — the threshold applied

**From MRIQC `dwi_group.tsv` (if `--mriqc-dir` is provided):**
All columns from the MRIQC group TSV are propagated with a `mriqc_` prefix (e.g. `mriqc_fd_mean`, `mriqc_snr_wm`).

When a QC file is absent for a given subject × session, QC columns are `NaN` and a warning is written to the run log.

---

## Handling Missing Data

Longitudinal neuroimaging studies inevitably have gaps: subjects miss timepoints, sessions fail QC, certain reconstruction workflows only ran on a subset of data. `qsi-extract` is designed around this reality.

The collation step builds a **complete subject × session × bundle grid** from all entities discovered across the entire derivative tree. Data is then left-joined onto this grid. Gaps produce:

- `NaN` in all scalar and QC columns for that cell
- `scalar_present = False`
- A `missing` or `partial` status in `run_log.tsv`

This means the output table is always rectangular and safe to pass directly to mixed-effects models or other longitudinal analysis tools that expect a complete index.

**`--missing-session-policy`** controls verbosity:
- `warn` (default): log and continue
- `ignore`: silently skip
- `error`: abort if any expected session is absent; useful for catching pipeline failures early

Sessions and subjects can also be explicitly enumerated with `--subjects` and `--sessions` to override the auto-discovery, which is useful if your BIDS dataset contains pilot subjects or sessions you want to exclude.

---

## Supported File Patterns

`qsi-extract` recognises the following file patterns during traversal. Patterns are checked in priority order within each category; the first match wins unless `--bundle-source` overrides.

**Bundle scalar files (priority order):**

1. `qsirecon/derivatives/qsirecon-*/sub-*/[ses-*/]dwi/*_bundle_means.tsv`
2. `qsirecon/derivatives/qsirecon-*/sub-*/[ses-*/]dwi/*bundles-*_scalarstats.csv`
3. `qsirecon/[sub-*/ses-*/]dwi/*_tractometry.csv`

**NODDI dwimap JSON sidecars:**

```
qsirecon/derivatives/qsirecon-*/sub-*/[ses-*/]dwi/
  *_model-noddi_param-icvf_dwimap.json
  *_model-noddi_param-isovf_dwimap.json
  *_model-noddi_param-od_dwimap.json
  *_model-noddi_desc-modulated_param-icvf_dwimap.json
```

**QSIPrep QC files (both naming conventions):**

```
qsiprep/sub-*/[ses-*/]dwi/
  *_desc-image_qc.tsv          (QSIPrep ≥1.0)
  *_desc-ImageQC_dwi.csv       (QSIPrep <1.0)
  *_desc-confounds_timeseries.tsv
```

All patterns are defined in `qsi_extract/layout/file_patterns.py` and can be inspected or extended without modifying other modules.

---

## Configuration

All CLI arguments can be supplied as a JSON config file passed with `--config`:

```json
{
  "qsiprep_dir": "/data/derivatives/qsiprep",
  "qsirecon_dir": "/data/derivatives/qsirecon",
  "output_dir": "/data/derivatives/qsi_extract",
  "mriqc_dir": "/data/derivatives/mriqc",
  "noddi_infant_threshold_months": 18,
  "noddi_expected_d_par": 1.7,
  "fd_censoring_threshold_mm": 0.5,
  "scalar_format": "wide",
  "write_parquet": true,
  "missing_session_policy": "warn",
  "bundle_source": "auto",
  "recon_suffixes": null
}
```

CLI arguments always take precedence over config file values. The config snapshot actually used for a run is written to `config_used.json` in the output directory for reproducibility.

---

## Package Architecture

```
qsi-extract/
│
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── qsi_extract/
│   ├── __init__.py                  # Extractor facade + version
│   ├── cli.py                       # argparse entry point
│   ├── config.py                    # ExtractorConfig dataclass
│   │
│   ├── layout/
│   │   ├── bids_layout.py           # BIDS tree traversal (pure pathlib)
│   │   └── file_patterns.py         # All glob patterns, versioned
│   │
│   ├── parsers/
│   │   ├── bundle_means.py          # bundle_means.tsv + scalarstats.csv
│   │   ├── tractometry.py           # TractSeg/Scilpy tractometry CSV
│   │   ├── dwimap_json.py           # *_dwimap.json sidecar extraction
│   │   └── qc.py                    # image_qc.tsv, confounds_timeseries.tsv, MRIQC
│   │
│   ├── collators/
│   │   ├── longitudinal.py          # Subject × session × bundle outer-join
│   │   └── metadata.py              # Version and acquisition metadata propagation
│   │
│   ├── flags/
│   │   └── noddi_assumptions.py     # d_par audit + modulated map check
│   │
│   ├── output/
│   │   ├── writers.py               # CSV + Parquet writers
│   │   └── data_dictionary.py       # Auto-generate column descriptions
│   │
│   └── utils/
│       ├── logging.py               # Structured per-subject warning aggregation
│       └── validation.py            # Schema checks before collation
│
└── tests/
    ├── fixtures/                    # Minimal synthetic BIDS tree
    │   ├── qsiprep/sub-01/ses-1mo/dwi/
    │   ├── qsirecon/derivatives/qsirecon-NODDI/sub-01/ses-1mo/dwi/
    │   └── mriqc/
    ├── test_layout.py
    ├── test_parsers.py
    ├── test_collators.py
    ├── test_flags.py
    └── test_cli.py
```

The design follows a strict **read → parse → collate → flag → write** pipeline with no circular dependencies between layers. Each parser returns a list of plain dicts; the collator is the only module that touches pandas. This makes individual parsers trivially testable against synthetic fixtures without a full BIDS tree.

---

## Development

```bash
git clone https://github.com/<your-org>/qsi-extract.git
cd qsi-extract
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Linting
ruff check qsi_extract/
ruff format qsi_extract/
```

### Running against a real dataset

```bash
qsi-extract \
  --qsiprep-dir  /path/to/qsiprep \
  --qsirecon-dir /path/to/qsirecon \
  --output-dir   /tmp/qsi_extract_test \
  -v
```

### Adding support for a new bundle scalar format

1. Add the glob pattern to `qsi_extract/layout/file_patterns.py`
2. Write a parser in `qsi_extract/parsers/` that returns `list[dict]` with at minimum the keys `subject`, `session`, `bundle`, `scalar`, `value`
3. Register the parser in `qsi_extract/layout/bids_layout.py`
4. Add fixtures and a test in `tests/`

---

## Known Limitations

- **Voxel-level extraction is out of scope.** `qsi-extract` works exclusively with bundle-level and ROI-level summary statistics already computed by QSIRecon. It does not extract scalars from NIfTI dwimap images — that would require `nibabel` and would be a separate tool.

- **TractSeg via QSIRecon vs. standalone.** If TractSeg was run inside a custom QSIRecon workflow, the tractometry output ends up in the QSIRecon derivative tree and is handled automatically. If TractSeg and Scilpy were run standalone outside QSIRecon, their output directory must be passed separately (planned for a future `--tractseg-dir` argument).

- **XCP-D confounds.** XCP-D censoring outputs are not yet ingested. FD-based censoring counts are currently derived from the QSIPrep confounds TSV. An `--xcpd-dir` argument is planned.

- **Multi-run sessions.** When a session contains multiple DWI runs that were preprocessed separately, `qsi-extract` picks the first matching QC file and logs a warning. Run-level disambiguation is planned.

- **Along-tract profiles.** Tractometry CSV files are currently collapsed to per-bundle means and standard deviations. Preserving the full along-tract node profile as a separate output is planned.

- **`dkimicro` / WMTI scalars** (`awf`, `rde`) were removed from QSIRecon in v1.2.0 and are not supported.

---

## Citation

If you use `qsi-extract` in your research, please cite the QSIPrep/QSIRecon paper:

> Cieslak, M., Cook, P. A., He, X., Yeh, F. C., Dhollander, T., Adebimpe, A., … & Satterthwaite, T. D. (2021). QSIPrep: an integrative platform for preprocessing and reconstructing diffusion MRI data. *Nature Methods*, 18(7), 775–778. https://doi.org/10.1038/s41592-021-01185-5

If you use NODDI outputs, cite:

> Zhang, H., Schneider, T., Wheeler-Kingshott, C. A., & Alexander, D. C. (2012). NODDI: practical in vivo neurite orientation dispersion and density imaging of the human brain. *NeuroImage*, 61(4), 1000–1016.

If you use tissue-fraction modulated NODDI maps (`noddi_modulated_present = True`), cite:

> Parker, C. S., Veale, T., Bocchetta, M., et al. (2021). Not all voxels are created equal: reducing estimation bias in regional NODDI metrics using tissue-weighted means. *NeuroImage*, 245, 118749.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
