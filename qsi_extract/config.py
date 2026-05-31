"""
qsi_extract.config
==================

All runtime configuration for qsi-extract in a single dataclass.

Config can be built from:
- Direct instantiation (Python API)
- A JSON file via ``ExtractorConfig.from_json()``
- CLI argument namespace via ``ExtractorConfig.from_args()``

CLI arguments always take precedence over values loaded from a JSON file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Literal, Optional


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

BundleSource = Literal["auto", "bundle_means", "scalarstats", "tractometry"]
ScalarFormat = Literal["long", "wide"]
MissingPolicy = Literal["warn", "error", "ignore"]


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExtractorConfig:
    """All settings that control a qsi-extract run.

    Parameters
    ----------
    qsiprep_dir:
        Root of the QSIPrep derivatives dataset (the ``qsiprep/`` folder).
    qsirecon_dir:
        Root of the QSIRecon derivatives dataset (the ``qsirecon/`` folder).
    output_dir:
        Directory to write all outputs; created if it does not exist.
    mriqc_dir:
        Optional path to MRIQC derivatives; enables MRIQC QC column
        propagation when provided.
    subjects:
        Restrict extraction to these subject labels (without the ``sub-``
        prefix).  ``None`` means all subjects discovered in the tree.
    sessions:
        Restrict extraction to these session labels (without the ``ses-``
        prefix).  ``None`` means all sessions discovered in the tree.
    recon_suffixes:
        Limit ingestion to these QSIRecon workflow suffix strings
        (e.g. ``["NODDI", "DTI"]``).  ``None`` means all suffixes found.
    bundle_source:
        Which bundle scalar file type to prefer.  ``"auto"`` checks
        ``bundle_means`` → ``scalarstats`` → ``tractometry`` in that order.
    scalar_format:
        ``"long"``  — one row per subject × session × bundle × scalar
        (default).
        ``"wide"``  — one row per subject × session × bundle, scalars as
        columns.
    noddi_infant_threshold_months:
        Sessions with ``session_age_months`` ≤ this value will receive a
        ``WARN:adult_default_d_par_in_infant`` flag when ``d_par == 1.7``.
        Default is 18 months.
    noddi_expected_d_par:
        The cohort-specific intrinsic diffusivity value you expect AMICO to
        have used.  Runs that deviate from this (and don't equal 1.7) receive
        a ``WARN:unexpected_d_par`` flag.  Default is 1.7 (adult default).
    fd_censoring_threshold_mm:
        Framewise displacement threshold (mm) used to compute
        ``qc_n_censored`` and ``qc_pct_censored`` from the confounds TSV.
        Default is 0.5 mm.
    missing_session_policy:
        How to handle absent sessions: ``"warn"`` (log and continue),
        ``"error"`` (raise RuntimeError), ``"ignore"`` (silently skip).
    write_parquet:
        Write a Parquet file in addition to CSV.  Requires ``pyarrow``.
    include_qc:
        Whether to ingest QC files.  Set ``False`` to skip QC entirely.
    include_data_dictionary:
        Whether to write the auto-generated data dictionary CSV.
    verbosity:
        Logging level: 0 = WARNING, 1 = INFO, 2 = DEBUG.
    """

    # Required
    qsiprep_dir: Path
    qsirecon_dir: Path
    output_dir: Path

    # Optional QC sources
    mriqc_dir: Optional[Path] = None

    # Filtering
    subjects: Optional[List[str]] = None
    sessions: Optional[List[str]] = None
    recon_suffixes: Optional[List[str]] = None

    # Extraction behaviour
    bundle_source: BundleSource = "auto"
    scalar_format: ScalarFormat = "long"

    # NODDI auditing
    noddi_infant_threshold_months: float = 18.0
    noddi_expected_d_par: float = 1.7

    # QC computation
    fd_censoring_threshold_mm: float = 0.5

    # Missing data
    missing_session_policy: MissingPolicy = "warn"

    # Output options
    write_parquet: bool = False
    include_qc: bool = True
    include_data_dictionary: bool = True

    # Logging
    verbosity: int = 0

    # -----------------------------------------------------------------------
    # Post-init coercion
    # -----------------------------------------------------------------------

    def __post_init__(self) -> None:
        self.qsiprep_dir = Path(self.qsiprep_dir)
        self.qsirecon_dir = Path(self.qsirecon_dir)
        self.output_dir = Path(self.output_dir)
        if self.mriqc_dir is not None:
            self.mriqc_dir = Path(self.mriqc_dir)

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def validate(self) -> None:
        """Raise ``ValueError`` or ``FileNotFoundError`` for bad config."""
        errors: list[str] = []

        for attr in ("qsiprep_dir", "qsirecon_dir"):
            p: Path = getattr(self, attr)
            if not p.exists():
                errors.append(f"{attr} does not exist: {p}")
            elif not p.is_dir():
                errors.append(f"{attr} is not a directory: {p}")

        if self.mriqc_dir is not None:
            if not self.mriqc_dir.exists():
                errors.append(f"mriqc_dir does not exist: {self.mriqc_dir}")

        if self.bundle_source not in ("auto", "bundle_means", "scalarstats", "tractometry"):
            errors.append(f"Invalid bundle_source: {self.bundle_source!r}")

        if self.scalar_format not in ("long", "wide"):
            errors.append(f"Invalid scalar_format: {self.scalar_format!r}")

        if self.missing_session_policy not in ("warn", "error", "ignore"):
            errors.append(f"Invalid missing_session_policy: {self.missing_session_policy!r}")

        if self.noddi_infant_threshold_months < 0:
            errors.append("noddi_infant_threshold_months must be non-negative")

        if self.fd_censoring_threshold_mm <= 0:
            errors.append("fd_censoring_threshold_mm must be positive")

        if errors:
            raise ValueError("ExtractorConfig validation failed:\n" + "\n".join(f"  • {e}" for e in errors))

        if self.write_parquet:
            try:
                import pyarrow  # noqa: F401
            except ImportError:
                raise ImportError(
                    "write_parquet=True requires pyarrow. "
                    "Install it with: pip install 'qsi-extract[parquet]'"
                )

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of all settings."""
        d = asdict(self)
        # Convert Path objects to strings
        for key in ("qsiprep_dir", "qsirecon_dir", "output_dir", "mriqc_dir"):
            if d[key] is not None:
                d[key] = str(d[key])
        return d

    def to_json(self, path: Path) -> None:
        """Write config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def from_json(cls, path: Path) -> "ExtractorConfig":
        """Load config from a JSON file."""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(**data)

    @classmethod
    def from_args(cls, args) -> "ExtractorConfig":
        """Build config from an ``argparse.Namespace``, skipping ``None`` values
        so that unset CLI arguments fall back to dataclass defaults."""
        kwargs = {k: v for k, v in vars(args).items() if v is not None}

        # argparse stores --no-qc as include_qc=False; handle flag inversion
        if hasattr(args, "no_qc"):
            kwargs["include_qc"] = not args.no_qc
        if hasattr(args, "no_data_dictionary"):
            kwargs["include_data_dictionary"] = not args.no_data_dictionary

        # Drop argparse-internal keys
        for drop in ("no_qc", "no_data_dictionary", "config", "verbose"):
            kwargs.pop(drop, None)

        if hasattr(args, "verbose") and args.verbose is not None:
            kwargs["verbosity"] = args.verbose

        return cls(**kwargs)
