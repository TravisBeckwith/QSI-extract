"""
qsi_extract.cli
===============

Command-line entry point for qsi-extract.

Invoked as ``qsi-extract`` after installation (see ``[project.scripts]``
in ``pyproject.toml``), or directly as ``python -m qsi_extract.cli``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qsi_extract import __version__
from qsi_extract.config import ExtractorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qsi-extract",
        description=(
            "Extract and collate diffusion MRI scalar outputs from QSIPrep "
            "and QSIRecon into tidy longitudinal tables."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Minimal run
  qsi-extract \\
    --qsiprep-dir  /data/derivatives/qsiprep \\
    --qsirecon-dir /data/derivatives/qsirecon \\
    --output-dir   /data/derivatives/qsi_extract

  # With MRIQC QC, wide format, and Parquet
  qsi-extract \\
    --qsiprep-dir  /data/derivatives/qsiprep \\
    --qsirecon-dir /data/derivatives/qsirecon \\
    --mriqc-dir    /data/derivatives/mriqc \\
    --output-dir   /data/derivatives/qsi_extract \\
    --scalar-format wide \\
    --parquet

  # Infant study: flag adult-default d_par under 18 months
  qsi-extract \\
    --qsiprep-dir  /data/derivatives/qsiprep \\
    --qsirecon-dir /data/derivatives/qsirecon \\
    --output-dir   /data/derivatives/qsi_extract \\
    --noddi-infant-threshold-months 18
""",
    )

    parser.add_argument("--version", action="version", version=f"qsi-extract {__version__}")

    # ----------------------------------------------------------------
    # Required
    # ----------------------------------------------------------------
    req = parser.add_argument_group("required arguments")
    req.add_argument(
        "--qsiprep-dir",
        metavar="PATH",
        type=Path,
        required=True,
        help="Root of the QSIPrep derivatives dataset (the qsiprep/ folder).",
    )
    req.add_argument(
        "--qsirecon-dir",
        metavar="PATH",
        type=Path,
        required=True,
        help="Root of the QSIRecon derivatives dataset (the qsirecon/ folder).",
    )
    req.add_argument(
        "--output-dir",
        metavar="PATH",
        type=Path,
        required=True,
        help="Directory to write all outputs. Created if it does not exist.",
    )

    # ----------------------------------------------------------------
    # Optional QC sources
    # ----------------------------------------------------------------
    qc = parser.add_argument_group("QC sources")
    qc.add_argument(
        "--mriqc-dir",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to MRIQC derivatives. Enables MRIQC IQM propagation.",
    )

    # ----------------------------------------------------------------
    # Filtering
    # ----------------------------------------------------------------
    filt = parser.add_argument_group("filtering")
    filt.add_argument(
        "--subjects",
        metavar="SUBJECT",
        nargs="+",
        default=None,
        help="Restrict to these subject labels (without 'sub-' prefix).",
    )
    filt.add_argument(
        "--sessions",
        metavar="SESSION",
        nargs="+",
        default=None,
        help="Restrict to these session labels (without 'ses-' prefix).",
    )
    filt.add_argument(
        "--recon-suffixes",
        metavar="SUFFIX",
        nargs="+",
        default=None,
        help="Restrict to these QSIRecon workflow suffix strings (e.g. NODDI DTI).",
    )

    # ----------------------------------------------------------------
    # Extraction behaviour
    # ----------------------------------------------------------------
    ext = parser.add_argument_group("extraction")
    ext.add_argument(
        "--bundle-source",
        choices=["auto", "bundle_means", "scalarstats", "tractometry"],
        default="auto",
        help=(
            "Which bundle scalar file type to prefer. 'auto' checks "
            "bundle_means → scalarstats → tractometry in priority order. "
            "(default: auto)"
        ),
    )
    ext.add_argument(
        "--scalar-format",
        choices=["long", "wide"],
        default="long",
        help=(
            "Output table shape. 'long': one row per sub×ses×bundle×scalar. "
            "'wide': one row per sub×ses×bundle, scalars as columns. "
            "(default: long)"
        ),
    )

    # ----------------------------------------------------------------
    # NODDI auditing
    # ----------------------------------------------------------------
    noddi = parser.add_argument_group("NODDI assumption auditing")
    noddi.add_argument(
        "--noddi-infant-threshold-months",
        metavar="N",
        type=float,
        default=18.0,
        dest="noddi_infant_threshold_months",
        help=(
            "Sessions with age_months ≤ N and d_par == 1.7 receive a "
            "WARN:adult_default_d_par_in_infant flag. (default: 18)"
        ),
    )
    noddi.add_argument(
        "--noddi-expected-d-par",
        metavar="VALUE",
        type=float,
        default=1.7,
        dest="noddi_expected_d_par",
        help=(
            "The intrinsic diffusivity value your cohort's AMICO runs used. "
            "Unexpected deviations are flagged. (default: 1.7)"
        ),
    )

    # ----------------------------------------------------------------
    # QC computation
    # ----------------------------------------------------------------
    qcomp = parser.add_argument_group("QC computation")
    qcomp.add_argument(
        "--fd-censoring-threshold",
        metavar="MM",
        type=float,
        default=0.5,
        dest="fd_censoring_threshold_mm",
        help="FD threshold (mm) for computing censored volume counts. (default: 0.5)",
    )

    # ----------------------------------------------------------------
    # Missing data
    # ----------------------------------------------------------------
    miss = parser.add_argument_group("missing data")
    miss.add_argument(
        "--missing-session-policy",
        choices=["warn", "error", "ignore"],
        default="warn",
        dest="missing_session_policy",
        help=(
            "How to handle absent sessions: warn (log and continue), "
            "error (abort), ignore (silently skip). (default: warn)"
        ),
    )

    # ----------------------------------------------------------------
    # Output options
    # ----------------------------------------------------------------
    out = parser.add_argument_group("output options")
    out.add_argument(
        "--parquet",
        action="store_true",
        default=False,
        dest="write_parquet",
        help="Write Parquet file in addition to CSV. Requires pyarrow.",
    )
    out.add_argument(
        "--no-qc",
        action="store_true",
        default=False,
        help="Skip QC file ingestion entirely.",
    )
    out.add_argument(
        "--no-data-dictionary",
        action="store_true",
        default=False,
        help="Skip auto-generated data dictionary.",
    )

    # ----------------------------------------------------------------
    # Config file
    # ----------------------------------------------------------------
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        default=None,
        help=(
            "JSON config file. Values are used as defaults; "
            "any explicit CLI argument overrides them."
        ),
    )

    # ----------------------------------------------------------------
    # Verbosity
    # ----------------------------------------------------------------
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity. Use -vv for DEBUG output.",
    )

    return parser


def main(argv=None) -> int:
    """Entry point for the ``qsi-extract`` command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Load base config from JSON file (if provided), then overlay CLI args
    # ------------------------------------------------------------------
    if args.config is not None:
        try:
            config = ExtractorConfig.from_json(args.config)
        except (json.JSONDecodeError, TypeError) as exc:
            parser.error(f"Failed to load config file {args.config}: {exc}")
            return 1  # unreachable but satisfies type checkers
        # Override with any explicitly set CLI values
        cli_overrides = {k: v for k, v in vars(args).items()
                         if v is not None and k not in ("config",)}
        for key, value in cli_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
        # Handle flag inversions
        config.include_qc = not args.no_qc
        config.include_data_dictionary = not args.no_data_dictionary
        config.verbosity = args.verbose
    else:
        config = ExtractorConfig.from_args(args)

    # ------------------------------------------------------------------
    # Validate and run
    # ------------------------------------------------------------------
    try:
        config.validate()
    except (ValueError, FileNotFoundError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    from qsi_extract._extractor import Extractor

    try:
        Extractor(config).run()
    except Exception as exc:
        print(f"ERROR: Run failed — {exc}", file=sys.stderr)
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
