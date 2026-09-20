"""Multi-format sensor data parsers for BloomPulse."""
from __future__ import annotations
import csv
import io
import json
from typing import Optional
import pandas as pd


class ParseError(Exception):
    """Raised when parsing fails with a user-actionable message."""
    pass


REQUIRED_COLUMNS = {"timestamp", "equipment_id", "temperature_c", "vibration_mm_s"}
OPTIONAL_COLUMNS = {"pressure_bar", "rpm"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


def _validate_dataframe(df: pd.DataFrame, min_rows: int = 0, max_rows: int = 500, default_equipment_id: str = "BRG-05-A") -> pd.DataFrame:
    """Validate parsed DataFrame has required columns and data."""
    if df.empty:
        raise ParseError("The uploaded file is empty.")

    cols = set(df.columns)
    missing = REQUIRED_COLUMNS - cols
    
    # If equipment_id is missing but we have a default, add it
    if "equipment_id" in missing:
        df["equipment_id"] = default_equipment_id
        missing = missing - {"equipment_id"}
    
    if missing:
        raise ParseError(
            f"File is missing required column(s): {', '.join(sorted(missing))}. "
            f"Expected columns: {', '.join(sorted(ALL_COLUMNS))}"
        )

    # Ensure numeric columns are numeric
    for col in ["temperature_c", "vibration_mm_s", "pressure_bar", "rpm"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            # Check for non-numeric values that became NaN
            if df[col].isna().sum() > 0:
                raise ParseError(f"Column '{col}' contains values that are not a number.")

    # Parse timestamps
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Check for NaT timestamps
        if df["timestamp"].isna().any():
            raise ParseError("Timestamp column contains invalid or missing values.")

    # Drop rows where all values are NaN
    df = df.dropna(how="all")

    if df.empty:
        raise ParseError("No valid data rows found after parsing.")

    if min_rows > 0 and len(df) < min_rows:
        raise ParseError(
            f"Need at least {min_rows} data rows for analysis, got {len(df)}. "
            "Upload a longer time series."
        )

    if len(df) > max_rows:
        raise ParseError(f"CSV has more than {max_rows} data rows. Split the file and retry.")

    return df


def parse_csv(raw: bytes, default_equipment_id: str = "BRG-05-A") -> pd.DataFrame:
    """Parse CSV bytes to validated DataFrame."""
    if not raw.strip():
        raise ParseError("The uploaded file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("File is not UTF-8 text. Export as plain CSV and retry.")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        raise ParseError(f"Failed to parse CSV: {e}")

    # Check for header-only CSV (columns exist but no data rows)
    if df.empty and len(df.columns) > 0:
        raise ParseError("No data rows found. Upload a CSV with at least one data row.")

    return _validate_dataframe(df, default_equipment_id=default_equipment_id)


def parse_jsonl(raw: bytes, default_equipment_id: str = "BRG-05-A") -> pd.DataFrame:
    """Parse JSONL bytes to validated DataFrame."""
    if not raw.strip():
        raise ParseError("The uploaded file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("File is not UTF-8 text.")

    lines = text.strip().split("\n")
    records = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ParseError(f"Line {i+1}: invalid JSON - {e}")

    if not records:
        raise ParseError("No valid JSON records found.")

    df = pd.DataFrame(records)
    return _validate_dataframe(df, default_equipment_id=default_equipment_id)


def parse_excel(raw: bytes, default_equipment_id: str = "BRG-05-A") -> pd.DataFrame:
    """Parse Excel (xlsx) bytes to validated DataFrame."""
    try:
        df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    except Exception as e:
        raise ParseError(f"Failed to parse Excel file: {e}")

    return _validate_dataframe(df, default_equipment_id=default_equipment_id)


def parse_parquet(raw: bytes, default_equipment_id: str = "BRG-05-A") -> pd.DataFrame:
    """Parse Parquet bytes to validated DataFrame."""
    try:
        df = pd.read_parquet(io.BytesIO(raw))
    except Exception as e:
        raise ParseError(f"Failed to parse Parquet file: {e}")

    return _validate_dataframe(df, default_equipment_id=default_equipment_id)


def parse_sensor_data(
    raw: bytes,
    filename: Optional[str] = None,
    default_equipment_id: str = "BRG-05-A",
) -> pd.DataFrame:
    """
    Parse sensor data from bytes, auto-detecting format from filename or content.

    Args:
        raw: Raw file bytes
        filename: Original filename (used for format detection)
        default_equipment_id: Default equipment ID if not in data

    Returns:
        Validated pandas DataFrame with required columns

    Raises:
        ParseError: If format unsupported or parsing fails
    """
    # Try filename-based detection first
    if filename:
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        if ext == "csv":
            return parse_csv(raw, default_equipment_id)
        elif ext in ("jsonl", "ndjson", "json"):
            return parse_jsonl(raw, default_equipment_id)
        elif ext in ("xlsx", "xls"):
            return parse_excel(raw, default_equipment_id)
        elif ext == "parquet":
            return parse_parquet(raw, default_equipment_id)

    # Fallback: content-based detection
    # Try JSONL first if it looks like JSONL (starts with { or [)
    trimmed = raw.lstrip()
    if trimmed.startswith(b"{") or trimmed.startswith(b"["):
        try:
            return parse_jsonl(raw, default_equipment_id)
        except ParseError:
            pass

    # Try CSV (most common)
    try:
        return parse_csv(raw, default_equipment_id)
    except ParseError:
        pass

    # Try JSONL (in case it doesn't start with { but is valid JSONL)
    try:
        return parse_jsonl(raw, default_equipment_id)
    except ParseError:
        pass

    # Try Excel/Parquet (check for ZIP magic bytes)
    if raw[:4] == b"PK\x03\x04":  # ZIP-based formats (xlsx, parquet)
        try:
            return parse_excel(raw, default_equipment_id)
        except ParseError:
            try:
                return parse_parquet(raw, default_equipment_id)
            except ParseError:
                pass

    raise ParseError(
        "Unsupported file format. Supported: CSV, JSONL, Excel (.xlsx), Parquet (.parquet)"
    )


def df_to_sensor_readings(df: pd.DataFrame, default_equipment_id: str = "BRG-05-A") -> list[dict]:
    """
    Convert validated DataFrame to list of sensor reading dicts for the anomaly engine.

    Args:
        df: Validated DataFrame from parse_sensor_data
        default_equipment_id: Fallback if equipment_id column missing

    Returns:
        List of dicts compatible with score_readings()
    """
    readings = []
    for _, row in df.iterrows():
        reading = {
            "timestamp": row["timestamp"].isoformat() if pd.notna(row["timestamp"]) else "",
            "equipment_id": row.get("equipment_id", default_equipment_id),
            "temperature_c": float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else 0.0,
            "vibration_mm_s": float(row["vibration_mm_s"]) if pd.notna(row["vibration_mm_s"]) else 0.0,
        }
        if "pressure_bar" in row and pd.notna(row["pressure_bar"]):
            reading["pressure_bar"] = float(row["pressure_bar"])
        if "rpm" in row and pd.notna(row["rpm"]):
            reading["rpm"] = float(row["rpm"])
        readings.append(reading)
    return readings