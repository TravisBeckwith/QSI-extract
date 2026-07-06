"""
qsi_extract._extractor
======================

The ``Extractor`` class is the top-level facade for a qsi-extract run.
It wires together the layout, parsers, collators, flags, and output modules
in the correct order, with structured per-subject logging throughout.

End users interact with this class directly; the sub-modules can also be
used independently for custom pipelines.
"""

from __future__ import annotations

import logging

import pandas as pd

from qsi_extract.collators.longitudinal import LongitudinalCollator
from qsi_extract.collators.metadata import MetadataCollator
from qsi_extract.config import ExtractorConfig
from qsi_extract.flags.noddi_assumptions import NODDIAssumptionFlagger
from qsi_extract.layout.bids_layout import BIDSLayout
from qsi_extract.output.data_dictionary import DataDictionaryBuilder
from qsi_extract.output.writers import OutputWriter
from qsi_extract.parsers.bundle_means import BundleMeansParser
from qsi_extract.parsers.dwimap_json import DwimapJsonParser
from qsi_extract.parsers.qc import QCParser
from qsi_extract.parsers.tractometry import TractometryParser
from qsi_extract.utils.logging import RunLogger, setup_logging

logger = logging.getLogger(__name__)


class Extractor:
    """Orchestrate a full qsi-extract run.

    Parameters
    ----------
    config:
        Fully populated ``ExtractorConfig``.  Call ``config.validate()``
        before passing it here, or let ``Extractor.__init__`` do it.

    Examples
    --------
    >>> config = ExtractorConfig(
    ...     qsiprep_dir="/data/derivatives/qsiprep",
    ...     qsirecon_dir="/data/derivatives/qsirecon",
    ...     output_dir="/data/derivatives/qsi_extract",
    ... )
    >>> df = Extractor(config).run()
    """

    def __init__(self, config: ExtractorConfig) -> None:
        config.validate()
        self.config = config
        setup_logging(config.verbosity)
        self._run_logger = RunLogger()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """Execute the full extraction pipeline.

        Returns
        -------
        pd.DataFrame
            The primary longitudinal scalar table (long or wide format,
            as specified in ``config.scalar_format``).  Also written to
            ``config.output_dir`` as CSV (and optionally Parquet).
        """
        cfg = self.config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("qsi-extract run starting")
        logger.info("  qsiprep_dir  : %s", cfg.qsiprep_dir)
        logger.info("  qsirecon_dir : %s", cfg.qsirecon_dir)
        logger.info("  output_dir   : %s", cfg.output_dir)

        # ----------------------------------------------------------
        # 1. Traverse BIDS trees
        # ----------------------------------------------------------
        logger.info("Step 1/6 — Traversing BIDS derivative trees")
        layout = BIDSLayout(
            qsiprep_dir=cfg.qsiprep_dir,
            qsirecon_dir=cfg.qsirecon_dir,
            subjects=cfg.subjects,
            sessions=cfg.sessions,
            recon_suffixes=cfg.recon_suffixes,
        )
        layout.discover()
        logger.info(
            "  Found %d subject(s), %d session(s)",
            len(layout.subjects),
            len(layout.sessions),
        )

        # ----------------------------------------------------------
        # 2. Parse scalar files
        # ----------------------------------------------------------
        logger.info("Step 2/6 — Parsing scalar files")
        scalar_records: list[dict] = []
        for subject, session, path, source_type in layout.iter_bundle_scalars(
            bundle_source=cfg.bundle_source
        ):
            try:
                if source_type == "tractometry":
                    records = TractometryParser(path, subject=subject, session=session).parse()
                else:
                    records = BundleMeansParser(path, subject=subject, session=session).parse()
                scalar_records.extend(records)
                self._run_logger.record_file(subject, session, "bundle_scalar", path)
            except Exception as exc:
                logger.warning("  [%s %s] Failed to parse %s: %s", subject, session, path.name, exc)
                self._run_logger.record_warning(subject, session, f"parse_error:{path.name}:{exc}")

        logger.info("  Parsed %d scalar records across all subjects/sessions", len(scalar_records))

        # ----------------------------------------------------------
        # 3. Parse NODDI JSON sidecars
        # ----------------------------------------------------------
        logger.info("Step 3/6 — Parsing dwimap JSON sidecars")
        sidecar_records: list[dict] = []
        for subject, session, json_paths in layout.iter_dwimap_jsons():
            try:
                records = DwimapJsonParser(
                    json_paths, subject=subject, session=session
                ).parse()
                sidecar_records.extend(records)
                self._run_logger.record_file(subject, session, "noddi_json", json_paths[0] if json_paths else None)
            except Exception as exc:
                logger.warning("  [%s %s] Failed to parse dwimap JSON: %s", subject, session, exc)
                self._run_logger.record_warning(subject, session, f"dwimap_json_error:{exc}")

        # ----------------------------------------------------------
        # 4. Parse QC files
        # ----------------------------------------------------------
        qc_records: list[dict] = []
        if cfg.include_qc:
            logger.info("Step 4/6 — Parsing QC files")
            for subject, session, qc_path, confounds_path in layout.iter_qc_files():
                try:
                    records = QCParser(
                        qc_path=qc_path,
                        confounds_path=confounds_path,
                        mriqc_dir=cfg.mriqc_dir,
                        subject=subject,
                        session=session,
                        fd_threshold=cfg.fd_censoring_threshold_mm,
                    ).parse()
                    qc_records.extend(records)
                    self._run_logger.record_file(subject, session, "qc", qc_path)
                    self._run_logger.record_file(subject, session, "confounds", confounds_path)
                except Exception as exc:
                    logger.warning("  [%s %s] Failed to parse QC: %s", subject, session, exc)
                    self._run_logger.record_warning(subject, session, f"qc_error:{exc}")
        else:
            logger.info("Step 4/6 — QC ingestion skipped (--no-qc)")

        # ----------------------------------------------------------
        # 5. Collate into longitudinal table
        # ----------------------------------------------------------
        logger.info("Step 5/6 — Collating longitudinal table")
        collator = LongitudinalCollator(
            scalar_format=cfg.scalar_format,
            missing_session_policy=cfg.missing_session_policy,
            run_logger=self._run_logger,
        )
        df = collator.collate(
            scalar_records=scalar_records,
            sidecar_records=sidecar_records,
            qc_records=qc_records,
            all_subjects=list(layout.subjects),
            all_sessions=list(layout.sessions),
        )

        # Apply NODDI assumption flags
        flagger = NODDIAssumptionFlagger(
            infant_threshold_months=cfg.noddi_infant_threshold_months,
            expected_d_par=cfg.noddi_expected_d_par,
        )
        df = flagger.apply(df)

        # Propagate version metadata
        meta_collator = MetadataCollator(layout)
        df = meta_collator.apply(df)

        logger.info("  Final table: %d rows × %d columns", len(df), len(df.columns))

        # ----------------------------------------------------------
        # 6. Write outputs
        # ----------------------------------------------------------
        logger.info("Step 6/6 — Writing outputs")
        writer = OutputWriter(cfg.output_dir)
        writer.write_table(df, write_parquet=cfg.write_parquet)

        if cfg.include_data_dictionary:
            dd = DataDictionaryBuilder(df).build()
            writer.write_data_dictionary(dd)

        writer.write_run_log(self._run_logger.to_dataframe())
        cfg.to_json(cfg.output_dir / "config_used.json")

        logger.info("Run complete. Outputs written to: %s", cfg.output_dir)
        return df
