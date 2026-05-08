"""
File loading helpers for the FP&A app.

Supports CSV and Excel because FP&A teams usually move data around in
spreadsheets. The loader keeps file-format logic away from the dashboard code.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd


def read_table(uploaded_file: BinaryIO | None, fallback_path: str | Path | None = None) -> pd.DataFrame:
    """
    Read CSV or Excel from a Streamlit upload object, or use a fallback sample file.

    Parameters
    ----------
    uploaded_file:
        Streamlit UploadedFile object, or None.
    fallback_path:
        Local CSV/XLSX path used when the user has not uploaded a file.
    """
    if uploaded_file is None and fallback_path is None:
        return pd.DataFrame()

    if uploaded_file is not None:
        name = uploaded_file.name.lower()
        raw = uploaded_file.getvalue()
        if name.endswith(".csv"):
            return pd.read_csv(BytesIO(raw))
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            return pd.read_excel(BytesIO(raw))
        raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")

    path = Path(fallback_path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported fallback file type: {path.suffix}")


def dollars(value: float) -> str:
    """Format dollar values consistently in the UI."""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def percent(value: float) -> str:
    """Format percentages consistently in the UI."""
    return f"{value:.1%}"


def coerce_download_name(name: str) -> str:
    """Create a safe file name for downloads."""
    return "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in name)
