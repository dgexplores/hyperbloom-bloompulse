"""Tests for multi-format sensor data parsers."""
import pytest
import pandas as pd
import io
import json
# Import from utils location for testing
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
from parsers import (
    parse_csv,
    parse_excel,
    parse_parquet,
    parse_jsonl,
    parse_sensor_data,
    ParseError,
)

# Sample CSV data
CSV_CONTENT = b"""timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar,rpm
2026-08-20T08:00:00,BRG-05-A,55.0,2.0,5.0,1750
2026-08-20T08:01:00,BRG-05-A,55.5,2.1,5.0,1750
2026-08-20T08:02:00,BRG-05-A,56.0,2.2,5.0,1750
2026-08-20T08:03:00,BRG-05-A,56.5,2.3,5.0,1750
2026-08-20T08:04:00,BRG-05-A,57.0,2.4,5.0,1750
2026-08-20T08:05:00,BRG-05-A,57.5,2.5,5.0,1750
2026-08-20T08:06:00,BRG-05-A,58.0,2.6,5.0,1750
2026-08-20T08:07:00,BRG-05-A,58.5,2.7,5.0,1750
"""

JSONL_CONTENT = b"""{"timestamp": "2026-08-20T08:00:00", "equipment_id": "BRG-05-A", "temperature_c": 55.0, "vibration_mm_s": 2.0, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:01:00", "equipment_id": "BRG-05-A", "temperature_c": 55.5, "vibration_mm_s": 2.1, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:02:00", "equipment_id": "BRG-05-A", "temperature_c": 56.0, "vibration_mm_s": 2.2, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:03:00", "equipment_id": "BRG-05-A", "temperature_c": 56.5, "vibration_mm_s": 2.3, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:04:00", "equipment_id": "BRG-05-A", "temperature_c": 57.0, "vibration_mm_s": 2.4, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:05:00", "equipment_id": "BRG-05-A", "temperature_c": 57.5, "vibration_mm_s": 2.5, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:06:00", "equipment_id": "BRG-05-A", "temperature_c": 58.0, "vibration_mm_s": 2.6, "pressure_bar": 5.0, "rpm": 1750}
{"timestamp": "2026-08-20T08:07:00", "equipment_id": "BRG-05-A", "temperature_c": 58.5, "vibration_mm_s": 2.7, "pressure_bar": 5.0, "rpm": 1750}
"""

def test_parse_csv_valid():
    df = parse_csv(CSV_CONTENT)
    assert len(df) == 8
    assert list(df.columns) == ["timestamp", "equipment_id", "temperature_c", "vibration_mm_s", "pressure_bar", "rpm"]
    assert df["equipment_id"].iloc[0] == "BRG-05-A"
    assert df["temperature_c"].iloc[0] == 55.0


def test_parse_csv_empty():
    with pytest.raises(ParseError, match="empty"):
        parse_csv(b"")


def test_parse_csv_missing_columns():
    bad_csv = b"""timestamp,equipment_id\n2026-08-20T08:00:00,BRG-05-A\n"""
    with pytest.raises(ParseError, match="missing required column"):
        parse_csv(bad_csv)


def test_parse_jsonl_valid():
    df = parse_jsonl(JSONL_CONTENT)
    assert len(df) == 8
    assert list(df.columns) == ["timestamp", "equipment_id", "temperature_c", "vibration_mm_s", "pressure_bar", "rpm"]
    assert df["equipment_id"].iloc[0] == "BRG-05-A"


def test_parse_jsonl_empty():
    with pytest.raises(ParseError, match="empty"):
        parse_jsonl(b"")


def test_parse_jsonl_invalid_json():
    bad_jsonl = b"""{"timestamp": "2026-08-20T08:00:00"}\nnot valid json\n"""
    with pytest.raises(ParseError, match="invalid JSON"):
        parse_jsonl(bad_jsonl)


def test_parse_excel_valid():
    # Create Excel in memory
    df = pd.read_csv(io.BytesIO(CSV_CONTENT))
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_content = excel_buffer.getvalue()

    parsed = parse_excel(excel_content)
    assert len(parsed) == 8
    assert list(parsed.columns) == ["timestamp", "equipment_id", "temperature_c", "vibration_mm_s", "pressure_bar", "rpm"]


def test_parse_excel_empty():
    import openpyxl
    wb = openpyxl.Workbook()
    buffer = io.BytesIO()
    wb.save(buffer)
    with pytest.raises(ParseError, match="empty"):
        parse_excel(buffer.getvalue())


def test_parse_parquet_valid():
    df = pd.read_csv(io.BytesIO(CSV_CONTENT))
    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, index=False)
    parquet_content = parquet_buffer.getvalue()

    parsed = parse_parquet(parquet_content)
    assert len(parsed) == 8
    assert list(parsed.columns) == ["timestamp", "equipment_id", "temperature_c", "vibration_mm_s", "pressure_bar", "rpm"]


def test_parse_parquet_empty():
    df = pd.DataFrame()
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    with pytest.raises(ParseError, match="empty"):
        parse_parquet(buffer.getvalue())


def test_parse_sensor_data_auto_detect_csv():
    df = parse_sensor_data(CSV_CONTENT, filename="data.csv")
    assert len(df) == 8


def test_parse_sensor_data_auto_detect_jsonl():
    df = parse_sensor_data(JSONL_CONTENT, filename="data.jsonl")
    assert len(df) == 8


def test_parse_sensor_data_auto_detect_excel():
    df_orig = pd.read_csv(io.BytesIO(CSV_CONTENT))
    excel_buffer = io.BytesIO()
    df_orig.to_excel(excel_buffer, index=False, engine='openpyxl')
    df = parse_sensor_data(excel_buffer.getvalue(), filename="data.xlsx")
    assert len(df) == 8


def test_parse_sensor_data_auto_detect_parquet():
    df_orig = pd.read_csv(io.BytesIO(CSV_CONTENT))
    parquet_buffer = io.BytesIO()
    df_orig.to_parquet(parquet_buffer, index=False)
    df = parse_sensor_data(parquet_buffer.getvalue(), filename="data.parquet")
    assert len(df) == 8


def test_parse_sensor_data_unknown_extension():
    # CSV content with .txt extension should still work via content detection
    df = parse_sensor_data(CSV_CONTENT, filename="data.txt")
    assert len(df) == 8


def test_parse_sensor_data_content_fallback():
    # No filename, should try to detect from content
    df = parse_sensor_data(CSV_CONTENT)
    assert len(df) == 8

    df = parse_sensor_data(JSONL_CONTENT)
    assert len(df) == 8