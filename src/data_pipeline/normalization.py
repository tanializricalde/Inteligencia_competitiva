"""Lossy keys used only in derived comparison columns."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalized_key(value: Any) -> Any:
    if value is None or value is pd.NA:
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except (TypeError, ValueError):
        pass
    decomposed = unicodedata.normalize("NFKD", str(value).strip().casefold())
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    result = NON_ALNUM.sub("_", ascii_text).strip("_")
    return result or pd.NA
