import logging
from io import BytesIO
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["sku", "name"]


def read_catalog_bytes(content: bytes) -> List[Dict[str, Any]]:
    """Read Excel bytes and return list of rows as dictionaries.

    NaN values are converted to None for easier validation.
    Lazily imports pandas/openpyxl to avoid startup import cost.
    """
    import pandas as pd

    df = pd.read_excel(BytesIO(content), engine="openpyxl")
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")
