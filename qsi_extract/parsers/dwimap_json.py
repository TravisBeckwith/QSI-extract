"""
qsi_extract.parsers.dwimap_json
=================================

Extract model fitting parameters from QSIRecon ``*_dwimap.json`` sidecars.

The JSON sidecars written by QSIRecon alongside each NIfTI scalar map
contain BIDS-style metadata including the model parameters used to produce
that map.  For AMICO NODDI, the most important field is ``d_par``
(intrinsic parallel diffusivity), which defaults to 1.7 µm²/ms (adult
white matter) and is known to be biased for infant tissue.

Key fields extracted per session
---------------------------------
NODDI (``model-noddi``):
    - ``d_par``       — intrinsic parallel diffusivity (µm²/ms)
    - ``d_iso``       — isotropic (free-water) diffusivity (µm²/ms)
    - ``modulated_present`` — whether desc-modulated variants were found

DTI (``model-tensor``):
    - Recorded for provenance; no infant-specific flags applied.

Output schema
-------------
One record per (subject, session) with all extracted fields prefixed by
``noddi_`` or ``dti_`` as appropriate::

    {
        "subject": "sub-01",
        "session": "ses-1mo",
        "noddi_d_par": 1.7,
        "noddi_d_iso": 3.0,
        "noddi_modulated_present": True,
        "dti_fitting_method": "WLS",
        ...
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# JSON keys that hold d_par across QSIRecon versions.
# The key name changed between releases; we check all known variants.
_DPAR_KEYS = ("d_par", "dpar", "IntrinsicDiffusivity", "intrinsic_diffusivity", "dPar")
_DISO_KEYS = ("d_iso", "diso", "IsotropicDiffusivity", "isotropic_diffusivity", "dIso")


class DwimapJsonParser:
    """Extract fitting parameters from a set of ``*_dwimap.json`` files.

    All JSON sidecars for a single subject/session are passed together.
    The parser aggregates them into a single record dict.

    Parameters
    ----------
    json_paths:
        List of ``*_dwimap.json`` paths for this subject/session.
    subject:
        Subject label.
    session:
        Session label.
    """

    def __init__(
        self,
        json_paths: list[Path],
        subject: str,
        session: str,
    ) -> None:
        self.json_paths = [Path(p) for p in json_paths]
        self.subject = subject
        self.session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> list[dict]:
        """Return a single-element list with one aggregated record.

        Returns
        -------
        list[dict]
            Always length 0 (no sidecars) or 1 (one record per sub/ses).
        """
        if not self.json_paths:
            return []

        record: dict[str, Any] = {
            "subject": self.subject,
            "session": self.session,
        }

        noddi_jsons = [p for p in self.json_paths if "model-noddi" in p.name]
        dti_jsons = [p for p in self.json_paths if "model-tensor" in p.name]

        if noddi_jsons:
            record.update(self._extract_noddi_params(noddi_jsons))

        if dti_jsons:
            record.update(self._extract_dti_params(dti_jsons))

        return [record]

    # ------------------------------------------------------------------
    # NODDI extraction
    # ------------------------------------------------------------------

    def _extract_noddi_params(self, paths: list[Path]) -> dict:
        """Extract NODDI fitting parameters from sidecar JSONs."""
        params: dict[str, Any] = {}

        # d_par and d_iso are the same across all param sidecars for one
        # session, so we read them from the first valid file.
        d_par: float | None = None
        d_iso: float | None = None
        modulated_found = False

        for path in paths:
            meta = self._load_json(path)
            if not meta:
                continue

            if d_par is None:
                d_par = self._get_first(meta, _DPAR_KEYS)
            if d_iso is None:
                d_iso = self._get_first(meta, _DISO_KEYS)
            if "desc-modulated" in path.name:
                modulated_found = True

        if d_par is not None:
            params["noddi_d_par"] = float(d_par)
        else:
            params["noddi_d_par"] = float("nan")
            logger.debug(
                "[%s %s] d_par not found in any NODDI sidecar", self.subject, self.session
            )

        if d_iso is not None:
            params["noddi_d_iso"] = float(d_iso)
        else:
            params["noddi_d_iso"] = float("nan")

        params["noddi_modulated_present"] = modulated_found

        # Record which sidecar files were found (for the run log)
        params["noddi_sidecar_count"] = len(paths)

        return params

    # ------------------------------------------------------------------
    # DTI extraction
    # ------------------------------------------------------------------

    def _extract_dti_params(self, paths: list[Path]) -> dict:
        """Extract DTI fitting parameters from sidecar JSONs."""
        params: dict[str, Any] = {}

        for path in sorted(paths):  # take first alphabetically (fa.json is most informative)
            meta = self._load_json(path)
            if not meta:
                continue

            # Record fitting method if present
            for key in ("FittingMethod", "fitting_method", "Method", "method"):
                if key in meta:
                    params["dti_fitting_method"] = str(meta[key])
                    break

            break  # only need metadata once

        params["dti_sidecar_count"] = len(paths)
        return params

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return {}

    @staticmethod
    def _get_first(meta: dict, keys: tuple) -> Any:
        """Return the value of the first matching key in meta."""
        for key in keys:
            if key in meta:
                return meta[key]
        return None
