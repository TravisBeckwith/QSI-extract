"""
qsi_extract.layout.bids_layout
================================

BIDS-aware traversal of QSIPrep and QSIRecon derivative trees using pure
``pathlib`` — no pybids dependency.

``BIDSLayout.discover()`` populates the sets of subjects, sessions, and
workflow suffixes found in the derivative trees.  The ``iter_*`` methods
yield (subject, session, path, …) tuples consumed by the parsers.

Version detection
-----------------
QSIPrep ≥1.0 writes DWI outputs in ``space-ACPC`` and QC files as
``*_desc-image_qc.tsv``.  Pre-1.0 used ``space-T1w`` and
``*_desc-ImageQC_dwi.csv``.  This module detects which convention is
present for each subject/session and stores the result in
``qsiprep_version_map`` for later propagation into output metadata.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, Optional, Set

from qsi_extract.layout import file_patterns as fp

logger = logging.getLogger(__name__)


class BIDSLayout:
    """Discover and iterate files in QSIPrep/QSIRecon derivative trees.

    Parameters
    ----------
    qsiprep_dir:
        Root of the QSIPrep derivative dataset.
    qsirecon_dir:
        Root of the QSIRecon derivative dataset.
    subjects:
        If provided, restrict discovery to these subject labels (without
        the ``sub-`` prefix).
    sessions:
        If provided, restrict discovery to these session labels (without
        the ``ses-`` prefix).
    recon_suffixes:
        If provided, restrict discovery to these QSIRecon workflow suffix
        strings.
    """

    def __init__(
        self,
        qsiprep_dir: Path,
        qsirecon_dir: Path,
        subjects: Optional[list[str]] = None,
        sessions: Optional[list[str]] = None,
        recon_suffixes: Optional[list[str]] = None,
    ) -> None:
        self.qsiprep_dir = Path(qsiprep_dir)
        self.qsirecon_dir = Path(qsirecon_dir)
        self._filter_subjects = set(subjects) if subjects else None
        self._filter_sessions = set(sessions) if sessions else None
        self._filter_recon_suffixes = set(recon_suffixes) if recon_suffixes else None

        # Populated by discover()
        self.subjects: Set[str] = set()
        self.sessions: Set[str] = set()
        self.recon_suffixes: Set[str] = set()

        # Maps (subject, session) -> "current" | "legacy" | "unknown"
        self.qsiprep_version_map: dict[tuple[str, str], str] = {}

        # dataset_description.json contents for version propagation
        self.qsiprep_dataset_desc: dict = {}
        self.qsirecon_dataset_descs: dict[str, dict] = {}  # keyed by recon suffix

        self._discovered = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Walk both derivative trees and populate subject/session sets."""
        self._discover_qsiprep()
        self._discover_qsirecon()
        self._discovered = True
        logger.debug(
            "Discovery complete: %d subjects, %d sessions, %d recon suffixes",
            len(self.subjects),
            len(self.sessions),
            len(self.recon_suffixes),
        )

    def _discover_qsiprep(self) -> None:
        """Walk qsiprep/ tree to find subjects and sessions."""
        desc_path = self.qsiprep_dir / fp.DATASET_DESCRIPTION
        if desc_path.exists():
            import json
            try:
                with open(desc_path, encoding="utf-8") as fh:
                    self.qsiprep_dataset_desc = json.load(fh)
            except Exception as exc:
                logger.warning("Could not read %s: %s", desc_path, exc)

        for sub_dir in sorted(self.qsiprep_dir.glob("sub-*")):
            if not sub_dir.is_dir():
                continue
            subject = sub_dir.name  # e.g. "sub-01"
            if self._filter_subjects and subject.removeprefix("sub-") not in self._filter_subjects:
                continue
            self.subjects.add(subject)

            # Session-level layout
            ses_dirs = sorted(sub_dir.glob("ses-*"))
            if ses_dirs:
                for ses_dir in ses_dirs:
                    if not ses_dir.is_dir():
                        continue
                    session = ses_dir.name  # e.g. "ses-1mo"
                    if self._filter_sessions and session.removeprefix("ses-") not in self._filter_sessions:
                        continue
                    self.sessions.add(session)
                    self._detect_qsiprep_version(subject, session, ses_dir / "dwi")
            else:
                # No session layer — use sentinel
                self.sessions.add("_no_session")
                self._detect_qsiprep_version(subject, "_no_session", sub_dir / "dwi")

    def _detect_qsiprep_version(self, subject: str, session: str, dwi_dir: Path) -> None:
        """Detect QSIPrep version convention from presence of version-specific files."""
        if not dwi_dir.exists():
            self.qsiprep_version_map[(subject, session)] = "unknown"
            return

        # Current (≥1.0): space-ACPC + desc-image_qc.tsv
        current_qc = list(dwi_dir.glob(fp.QSIPREP_IMAGE_QC["current"]))
        if current_qc:
            self.qsiprep_version_map[(subject, session)] = "current"
            return

        # Legacy (<1.0): space-T1w + desc-ImageQC_dwi.csv
        legacy_qc = list(dwi_dir.glob(fp.QSIPREP_IMAGE_QC["legacy"]))
        if legacy_qc:
            self.qsiprep_version_map[(subject, session)] = "legacy"
            return

        self.qsiprep_version_map[(subject, session)] = "unknown"

    def _discover_qsirecon(self) -> None:
        """Walk qsirecon/derivatives/ tree to find recon suffixes."""
        import json

        deriv_dir = self.qsirecon_dir / "derivatives"
        if not deriv_dir.exists():
            # Some setups put recon outputs directly under qsirecon/
            deriv_dir = self.qsirecon_dir

        for recon_dir in sorted(deriv_dir.glob("qsirecon-*")):
            if not recon_dir.is_dir():
                continue
            suffix = recon_dir.name.removeprefix("qsirecon-")
            if self._filter_recon_suffixes and suffix not in self._filter_recon_suffixes:
                continue
            self.recon_suffixes.add(suffix)

            # Read dataset_description.json for version info
            desc_path = recon_dir / fp.DATASET_DESCRIPTION
            if desc_path.exists():
                try:
                    with open(desc_path, encoding="utf-8") as fh:
                        self.qsirecon_dataset_descs[suffix] = json.load(fh)
                except Exception as exc:
                    logger.warning("Could not read %s: %s", desc_path, exc)

    # ------------------------------------------------------------------
    # Iterators
    # ------------------------------------------------------------------

    def iter_bundle_scalars(
        self, bundle_source: str = "auto"
    ) -> Iterator[tuple[str, str, Path, str]]:
        """Yield ``(subject, session, path, source_type)`` for every bundle
        scalar file found in the QSIRecon derivative tree.

        Parameters
        ----------
        bundle_source:
            ``"auto"`` checks in priority order; otherwise restricts to
            the named source type.

        Yields
        ------
        subject : str
            Subject label (e.g. ``"sub-01"``).
        session : str
            Session label (e.g. ``"ses-1mo"``), or ``"_no_session"``.
        path : Path
            Absolute path to the scalar file.
        source_type : str
            One of ``"bundle_means"``, ``"scalarstats"``, ``"tractometry"``.
        """
        self._require_discovered()

        patterns = (
            fp.BUNDLE_SCALAR_PRIORITY
            if bundle_source == "auto"
            else [(bundle_source, dict(fp.BUNDLE_SCALAR_PRIORITY)[bundle_source])]
        )

        deriv_dir = self.qsirecon_dir / "derivatives"
        if not deriv_dir.exists():
            deriv_dir = self.qsirecon_dir

        for recon_dir in sorted(deriv_dir.glob("qsirecon-*")):
            if not recon_dir.is_dir():
                continue
            suffix = recon_dir.name.removeprefix("qsirecon-")
            if self._filter_recon_suffixes and suffix not in self._filter_recon_suffixes:
                continue

            for sub_dir in sorted(recon_dir.glob("sub-*")):
                if not sub_dir.is_dir():
                    continue
                subject = sub_dir.name
                if self._filter_subjects and subject.removeprefix("sub-") not in self._filter_subjects:
                    continue

                ses_dirs = sorted(sub_dir.glob("ses-*"))
                search_dirs = (
                    [(ses_dir.name, ses_dir / "dwi") for ses_dir in ses_dirs if ses_dir.is_dir()]
                    if ses_dirs
                    else [("_no_session", sub_dir / "dwi")]
                )

                for session, dwi_dir in search_dirs:
                    if self._filter_sessions and session.removeprefix("ses-") not in self._filter_sessions:
                        continue
                    if not dwi_dir.exists():
                        continue

                    for source_type, pattern in patterns:
                        matches = sorted(dwi_dir.glob(pattern))
                        if matches:
                            for match in matches:
                                yield subject, session, match, source_type
                            if bundle_source == "auto":
                                break  # found highest-priority type; stop

    def iter_dwimap_jsons(
        self,
    ) -> Iterator[tuple[str, str, list[Path]]]:
        """Yield ``(subject, session, [json_paths])`` for NODDI dwimap sidecars.

        All NODDI param JSON sidecars for a given subject/session are
        grouped and returned together so the parser can extract all fitting
        parameters in one pass.

        Yields
        ------
        subject : str
        session : str
        json_paths : list[Path]
            All ``*_model-noddi_*_dwimap.json`` files found for this
            subject/session across all recon suffix subdatasets.
        """
        self._require_discovered()

        deriv_dir = self.qsirecon_dir / "derivatives"
        if not deriv_dir.exists():
            deriv_dir = self.qsirecon_dir

        # Collect all NODDI JSON paths grouped by (subject, session)
        grouped: dict[tuple[str, str], list[Path]] = {}

        for recon_dir in sorted(deriv_dir.glob("qsirecon-*")):
            if not recon_dir.is_dir():
                continue
            suffix = recon_dir.name.removeprefix("qsirecon-")
            if self._filter_recon_suffixes and suffix not in self._filter_recon_suffixes:
                continue

            for sub_dir in sorted(recon_dir.glob("sub-*")):
                subject = sub_dir.name
                if self._filter_subjects and subject.removeprefix("sub-") not in self._filter_subjects:
                    continue

                ses_dirs = sorted(sub_dir.glob("ses-*"))
                search_dirs = (
                    [(ses_dir.name, ses_dir / "dwi") for ses_dir in ses_dirs if ses_dir.is_dir()]
                    if ses_dirs
                    else [("_no_session", sub_dir / "dwi")]
                )

                for session, dwi_dir in search_dirs:
                    if self._filter_sessions and session.removeprefix("ses-") not in self._filter_sessions:
                        continue
                    if not dwi_dir.exists():
                        continue

                    key = (subject, session)
                    if key not in grouped:
                        grouped[key] = []

                    # Collect all noddi dwimap JSON files
                    for param in fp.NODDI_DWIMAP_JSON_PARAMS + fp.NODDI_MODULATED_PARAMS:
                        if "modulated" in param:
                            pattern = fp.NODDI_MODULATED_JSON_PATTERN.format(
                                param=param.replace("modulated-", "")
                            )
                        else:
                            pattern = fp.NODDI_DWIMAP_JSON_PATTERN.format(param=param)
                        grouped[key].extend(dwi_dir.glob(pattern))

        for (subject, session), paths in sorted(grouped.items()):
            if paths:
                yield subject, session, list(set(paths))  # deduplicate

    def iter_qc_files(
        self,
    ) -> Iterator[tuple[str, str, Optional[Path], Optional[Path]]]:
        """Yield ``(subject, session, qc_path, confounds_path)`` for QSIPrep
        QC files.

        Either ``qc_path`` or ``confounds_path`` may be ``None`` if the
        file was not found.  The caller is responsible for handling ``None``.

        Yields
        ------
        subject : str
        session : str
        qc_path : Path or None
            ``*_desc-image_qc.tsv`` (current) or ``*_desc-ImageQC_dwi.csv``
            (legacy).
        confounds_path : Path or None
            ``*_desc-confounds_timeseries.tsv``.
        """
        self._require_discovered()

        for sub_dir in sorted(self.qsiprep_dir.glob("sub-*")):
            if not sub_dir.is_dir():
                continue
            subject = sub_dir.name
            if self._filter_subjects and subject.removeprefix("sub-") not in self._filter_subjects:
                continue

            ses_dirs = sorted(sub_dir.glob("ses-*"))
            search_dirs = (
                [(ses_dir.name, ses_dir / "dwi") for ses_dir in ses_dirs if ses_dir.is_dir()]
                if ses_dirs
                else [("_no_session", sub_dir / "dwi")]
            )

            for session, dwi_dir in search_dirs:
                if self._filter_sessions and session.removeprefix("ses-") not in self._filter_sessions:
                    continue
                if not dwi_dir.exists():
                    yield subject, session, None, None
                    continue

                version = self.qsiprep_version_map.get((subject, session), "current")

                # QC file
                qc_pattern = fp.QSIPREP_IMAGE_QC.get(version, fp.QSIPREP_IMAGE_QC["current"])
                qc_matches = sorted(dwi_dir.glob(qc_pattern))
                # Fallback: try the other convention if primary not found
                if not qc_matches:
                    alt_version = "legacy" if version == "current" else "current"
                    qc_matches = sorted(dwi_dir.glob(fp.QSIPREP_IMAGE_QC[alt_version]))
                qc_path = qc_matches[0] if qc_matches else None

                # Confounds file
                confounds_matches = sorted(
                    dwi_dir.glob(fp.QSIPREP_CONFOUNDS["current"])
                )
                if not confounds_matches:
                    confounds_matches = sorted(
                        dwi_dir.glob(fp.QSIPREP_CONFOUNDS["legacy"])
                    )
                confounds_path = confounds_matches[0] if confounds_matches else None

                yield subject, session, qc_path, confounds_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_discovered(self) -> None:
        if not self._discovered:
            raise RuntimeError(
                "BIDSLayout.discover() must be called before iterating. "
                "Did you forget to call layout.discover()?"
            )

    def get_sessions_tsv(self, subject: str) -> Optional[Path]:
        """Return path to ``<subject>_sessions.tsv`` if it exists."""
        for pat in fp.SESSIONS_TSV_PATTERNS:
            candidate = self.qsiprep_dir / subject / pat.format(subject=subject)
            if candidate.exists():
                return candidate
        return None
