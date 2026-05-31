"""
qsi_extract.output.writers
============================

Write the primary table, data dictionary, and run log to disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TABLE_STEM = "scalars_longitudinal"


class OutputWriter:
    """Write qsi-extract outputs to *output_dir*.

    Parameters
    ----------
    output_dir:
        Directory to write all files.  Must already exist.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # Primary scalar table
    # ------------------------------------------------------------------

    def write_table(self, df: pd.DataFrame, write_parquet: bool = False) -> None:
        """Write the main longitudinal table as CSV (and optionally Parquet)."""
        csv_path = self.output_dir / f"{_TABLE_STEM}.csv"
        df.to_csv(csv_path, index=False)
        logger.info("Wrote CSV: %s (%d rows)", csv_path, len(df))

        if write_parquet:
            parquet_path = self.output_dir / f"{_TABLE_STEM}.parquet"
            try:
                df.to_parquet(parquet_path, index=False)
                logger.info("Wrote Parquet: %s", parquet_path)
            except ImportError:
                logger.error(
                    "pyarrow is required for Parquet output. "
                    "Install with: pip install 'qsi-extract[parquet]'"
                )

    # ------------------------------------------------------------------
    # Data dictionary
    # ------------------------------------------------------------------

    def write_data_dictionary(self, dd: pd.DataFrame) -> None:
        """Write the auto-generated data dictionary CSV."""
        path = self.output_dir / "data_dictionary.csv"
        dd.to_csv(path, index=False)
        logger.info("Wrote data dictionary: %s (%d columns documented)", path, len(dd))

    # ------------------------------------------------------------------
    # Run log
    # ------------------------------------------------------------------

    def write_run_log(self, log_df: pd.DataFrame) -> None:
        """Write the per-subject/session run log TSV."""
        path = self.output_dir / "run_log.tsv"
        log_df.to_csv(path, sep="\t", index=False)
        logger.info("Wrote run log: %s", path)
