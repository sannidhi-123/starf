"""Tests for CAN dataset loaders (Car-Hacking and OTIDS)."""

from __future__ import annotations

from stark.data.loaders.car_hacking import CarHackingLoader
from stark.data.loaders.otids import OTIDSLoader
from stark.schema import validate


def _write_file(path, lines: list[str]):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_car_hacking_ragged_dlc3_padding_and_hex_id(tmp_path):
    """Test ragged row with DLC=3 pads to -1 and converts hex 0316 to 790."""
    line = "1478198376.389427, 0316, 3, 05, 21, 68, R"
    file_path = _write_file(tmp_path / "Normal_run.csv", [line])

    loader = CarHackingLoader()
    df, dropped = loader.load_file(file_path)

    assert len(df) == 1
    assert dropped["dlc_mismatch"] == 0
    row = df.iloc[0]

    # Verify 0316 -> 790
    assert row["can_id"] == 790

    # Verify DLC
    assert row["dlc"] == 3

    # Verify bytes: 05, 21, 68 -> 5, 33, 104
    assert row["data_0"] == 5
    assert row["data_1"] == 33
    assert row["data_2"] == 104

    # Verify Rule 1: Missing bytes padded to -1
    for k in range(3, 8):
        assert row[f"data_{k}"] == -1

    # Verify metadata
    assert row["label"] == 0
    assert row["attack_type"] == "normal"
    assert row["label_quality"] == "frame"
    assert not row["is_remote"]
    validate(df)


def test_car_hacking_dos_attack_mapping(tmp_path):
    """Test Car-Hacking DoS file maps 'T' flag to attack_type='dos' and label=1."""
    line = "1478198376.389427, 0000, 8, 00, 00, 00, 00, 00, 00, 00, 00, T"
    file_path = _write_file(tmp_path / "DoS_dataset.csv", [line])

    loader = CarHackingLoader()
    df, _ = loader.load_file(file_path)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["can_id"] == 0
    assert row["attack_type"] == "dos"
    assert row["label"] == 1
    validate(df)


def test_otids_rtr_flag_detection(tmp_path):
    """Test OTIDS Remote Transmission Request (RTR) sets is_remote=True."""
    # Tagged format
    line_tagged = "Timestamp: 1479106721.467499    ID: 0130    DLC: 0    Remote"
    file_tagged = _write_file(tmp_path / "normal_run.txt", [line_tagged])

    loader = OTIDSLoader()
    df_tagged, _ = loader.load_file(file_tagged)

    assert len(df_tagged) == 1
    assert df_tagged.iloc[0]["is_remote"]
    assert df_tagged.iloc[0]["dlc"] == 0
    for k in range(8):
        assert df_tagged.iloc[0][f"data_{k}"] == -1

    # Delimited format with RTR
    line_delim = "1479106721.467499, 0130, 0, RTR"
    file_delim = _write_file(tmp_path / "normal_run_delim.txt", [line_delim])
    df_delim, _ = loader.load_file(file_delim)
    assert len(df_delim) == 1
    assert df_delim.iloc[0]["is_remote"]


def test_otids_label_quality_design_rules(tmp_path):
    """Test OTIDS design rule: window for fuzzy & impersonation, frame for DoS."""
    loader = OTIDSLoader()

    # DoS -> frame
    file_dos = _write_file(
        tmp_path / "DoS_dataset.txt",
        ["Timestamp: 1479106721.100000 ID: 0000 DLC: 8 00 00 00 00 00 00 00 00"],
    )
    df_dos, _ = loader.load_file(file_dos)
    assert df_dos.iloc[0]["attack_type"] == "dos"
    assert df_dos.iloc[0]["label_quality"] == "frame"

    # Fuzzy -> window
    file_fuzzy = _write_file(
        tmp_path / "Fuzzy_dataset.txt",
        ["Timestamp: 1479106721.100000 ID: 0153 DLC: 8 11 22 33 44 55 66 77 88"],
    )
    df_fuzzy, _ = loader.load_file(file_fuzzy)
    assert df_fuzzy.iloc[0]["attack_type"] == "fuzzy"
    assert df_fuzzy.iloc[0]["label_quality"] == "window"

    # Impersonation -> window
    file_imp = _write_file(
        tmp_path / "Impersonation_dataset.txt",
        ["Timestamp: 1479106721.100000 ID: 0316 DLC: 8 05 64 00 00 00 00 00 00"],
    )
    df_imp, _ = loader.load_file(file_imp)
    assert df_imp.iloc[0]["attack_type"] == "impersonation"
    assert df_imp.iloc[0]["label_quality"] == "window"


def test_loader_row_count_within_1_percent(tmp_path):
    """Test that clean parsing yields row count within 1% of raw file lines."""
    lines = []
    base_ts = 1478198000.0
    for i in range(1000):
        ts = base_ts + i * 0.001
        lines.append(f"{ts:.6f}, 0316, 8, 05, 21, 68, 09, 21, 21, 00, 6f, R")

    file_path = _write_file(tmp_path / "Normal_1000.csv", lines)
    loader = CarHackingLoader()
    df, dropped = loader.load_file(file_path)

    assert len(df) == 1000
    assert abs(len(df) - 1000) / 1000 <= 0.01
    assert sum(dropped.values()) == 0
