"""Strict validation for CSV-backed detection inputs."""

import pytest

from app.modules.detection.service import _csv_to_frames


def test_car_hacking_hex_ids_are_parsed_as_hex():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "data" / "samples" / "demo_normal.csv"
    )
    frames = _csv_to_frames(source)
    assert frames
    assert frames[0]["can_id"] == 0x140


def test_csv_invalid_timestamp_is_rejected_with_row_number(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("Timestamp,CAN ID,DLC\nNaN,0140,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row 2.*timestamp"):
        _csv_to_frames(source)


def test_csv_payload_length_must_match_dlc(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("Timestamp,CAN ID,DLC,DATA[0]\n0.1,0140,2,FF\n", encoding="utf-8")
    with pytest.raises(ValueError, match="payload has 1 bytes but DLC is 2"):
        _csv_to_frames(source)
