"""
qsi_extract.flags.noddi_assumptions
======================================

Audit NODDI model fitting assumptions and write flag columns.

Flag logic
----------
The ``noddi_d_par_flag`` column receives one of the following values:

``OK:custom_d_par_matches_expected``
    ``d_par`` was found in the sidecar and matches ``expected_d_par``
    (and is not the adult default of 1.7).  This is the ideal case for a
    study that has explicitly set a cohort-appropriate diffusivity.

``INFO:adult_default_d_par``
    ``d_par == 1.7`` and the session age is above the infant threshold
    (or age is unknown).  The default was used, which is appropriate for
    adult data but may warrant documentation.

``WARN:adult_default_d_par_in_infant``
    ``d_par == 1.7`` and ``session_age_months <= infant_threshold_months``.
    The adult default was applied to infant data — the most important flag
    for this study.

``WARN:unexpected_d_par``
    ``d_par`` does not equal 1.7 and does not match ``expected_d_par``.
    Unexpected deviation from both the default and the study protocol.

``UNKNOWN:sidecar_missing``
    No NODDI sidecar JSON was found; ``d_par`` is NaN.

The flag is applied **per session** (broadcast across all bundles for that
session, since d_par is a global fitting parameter, not per-bundle).
"""

from __future__ import annotations

import logging
from math import isnan

import pandas as pd

logger = logging.getLogger(__name__)

_ADULT_DEFAULT_DPAR = 1.7
_FLAG_COL = "noddi_d_par_flag"


class NODDIAssumptionFlagger:
    """Apply NODDI assumption audit flags to the primary table.

    Parameters
    ----------
    infant_threshold_months:
        Sessions at or below this age (months) trigger the infant warning
        when ``d_par == 1.7``.
    expected_d_par:
        The intrinsic diffusivity value the study protocol intended to use.
        Set to ``1.7`` to suppress the unexpected-deviation flag (i.e. you
        accept the adult default for your cohort).
    """

    def __init__(
        self,
        infant_threshold_months: float = 18.0,
        expected_d_par: float = 1.7,
    ) -> None:
        self.infant_threshold_months = infant_threshold_months
        self.expected_d_par = expected_d_par

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ``noddi_d_par_flag`` column to *df* and return it.

        If neither ``noddi_d_par`` nor ``session_age_months`` is present
        in the DataFrame, the column is added with ``"UNKNOWN:no_noddi_data"``
        for all rows and a warning is logged.
        """
        if "noddi_d_par" not in df.columns:
            logger.warning(
                "noddi_d_par column not found — "
                "NODDI assumption flags will be 'UNKNOWN:no_noddi_data'"
            )
            df[_FLAG_COL] = "UNKNOWN:no_noddi_data"
            return df

        df[_FLAG_COL] = df.apply(self._flag_row, axis=1)

        # Summary log
        flag_counts = df[_FLAG_COL].value_counts().to_dict()
        logger.info("NODDI d_par flag summary: %s", flag_counts)

        # Warn loudly if any infant sessions have adult default
        n_infant_warn = (df[_FLAG_COL] == "WARN:adult_default_d_par_in_infant").sum()
        if n_infant_warn > 0:
            logger.warning(
                "%d rows flagged WARN:adult_default_d_par_in_infant — "
                "adult d_par=1.7 was used in sessions ≤ %.0f months old",
                n_infant_warn,
                self.infant_threshold_months,
            )

        return df

    # ------------------------------------------------------------------
    # Row-level flag logic
    # ------------------------------------------------------------------

    def _flag_row(self, row: pd.Series) -> str:
        """Compute the flag value for one row."""
        d_par = row.get("noddi_d_par", float("nan"))
        age = row.get("session_age_months", float("nan"))

        # Missing sidecar
        try:
            if isnan(float(d_par)):
                return "UNKNOWN:sidecar_missing"
        except (TypeError, ValueError):
            return "UNKNOWN:sidecar_missing"

        d_par = float(d_par)

        # Adult default path
        if abs(d_par - _ADULT_DEFAULT_DPAR) < 1e-6:
            try:
                age_f = float(age)
                is_infant = not isnan(age_f) and age_f <= self.infant_threshold_months
            except (TypeError, ValueError):
                is_infant = False

            if is_infant:
                return "WARN:adult_default_d_par_in_infant"
            else:
                return "INFO:adult_default_d_par"

        # Non-default d_par
        if abs(d_par - self.expected_d_par) < 1e-6:
            return "OK:custom_d_par_matches_expected"

        return f"WARN:unexpected_d_par:{d_par:.4f}"
