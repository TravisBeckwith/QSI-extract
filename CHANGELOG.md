# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial package scaffold: `layout`, `parsers`, `collators`, `flags`, `output`, `utils` modules
- `pyproject.toml` with setuptools-scm versioning
- README with full usage documentation, output schema, and architecture overview
- Synthetic test fixtures for unit testing without a real BIDS dataset

## [0.1.0] — TBD

_First functional release — planned features:_

- BIDS-aware traversal of QSIPrep (≥1.0 and <1.0) and QSIRecon derivative trees
- Parsing of `bundle_means.tsv`, `*_scalarstats.csv`, and `Tractometry.csv`
- NODDI `d_par` auditing from `*_dwimap.json` sidecars
- QC propagation from `desc-image_qc.tsv`, confounds timeseries, and MRIQC group TSV
- Longitudinal collation with outer-join gap handling
- CSV and Parquet output
- Auto-generated data dictionary
- CLI entry point `qsi-extract`
