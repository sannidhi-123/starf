"""Car-Hacking Dataset loader for STARK."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from stark.data.loaders.base import BaseCANLoader


def _parse_hex_byte(token: str) -> int:
    """Parse a single hex byte string (e.g. '0F' or '0x0f') into an int in [0, 255]."""
    tok = token.strip()
    if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,2}", tok):
        raise ValueError(f"Invalid byte token: {token}")
    val = int(tok, 16)
    if val < 0 or val > 255:
        raise ValueError(f"Byte value out of range: {val}")
    return val


def _payload_tokens(fields: list[str], dlc: int) -> list[str]:
    """Extract payload tokens according to DLC, handling ragged rows."""
    if dlc == 0:
        return []
    payload_fields = fields[3:-1]
    if len(payload_fields) == dlc:
        return payload_fields
    if len(payload_fields) == 1:
        payload = payload_fields[0].strip()
        if not payload:
            return []
        if re.search(r"\s", payload):
            return payload.split()
        contiguous = payload[2:] if payload.lower().startswith("0x") else payload
        if len(contiguous) == dlc * 2 and re.fullmatch(r"[0-9a-fA-F]*", contiguous):
            return [contiguous[i : i + 2] for i in range(0, len(contiguous), 2)]
        return [payload]
    return payload_fields


def _map_attack_type(path: Path | None) -> str:
    """Map filename or path to canonical attack type."""
    if path is None:
        return "unknown"
    normalized = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    if "dos" in normalized:
        return "dos"
    if "fuzzy" in normalized:
        return "fuzzy"
    if "gear" in normalized:
        return "gear_spoof"
    if "rpm" in normalized:
        return "rpm_spoof"
    if "impersonation" in normalized:
        return "impersonation"
    if "replay" in normalized:
        return "replay"
    if "normal" in normalized:
        return "normal"
    return "unknown"


class CarHackingLoader(BaseCANLoader):
    """Loader for the Korea University HCRL Car-Hacking CAN dataset."""

    def parse_line(
        self,
        line: str,
        capture_name: str,
        path: Path | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a single raw Car-Hacking line into a canonical record."""
        try:
            fields = [
                f.strip() for f in next(csv.reader([line], skipinitialspace=True))
            ]
        except (csv.Error, StopIteration):
            fields = line.split()

        if len(fields) == 1 and " " in fields[0]:
            fields = fields[0].split()

        if len(fields) < 4:
            return None, "unparseable"

        try:
            dlc = int(fields[2], 10)
        except ValueError:
            return None, "corrupted"

        if dlc < 0 or dlc > 8:
            return None, "dlc_out_of_range"

        try:
            timestamp = float(fields[0])
            if not math.isfinite(timestamp) or timestamp < 0:
                return None, "corrupted"
            can_id = int(fields[1], 16)
            if can_id < 0 or can_id > 0x1FFFFFFF:
                return None, "corrupted"
        except (ValueError, OverflowError):
            return None, "corrupted"

        flag = fields[-1].strip().upper()
        if flag not in {"R", "T"}:
            return None, "corrupted"

        tokens = _payload_tokens(fields, dlc)
        if len(tokens) != dlc:
            return None, "dlc_mismatch"

        try:
            payload = [_parse_hex_byte(tok) for tok in tokens]
        except ValueError:
            return None, "corrupted"

        # Rule 1: Missing bytes (DLC < 8) are stored as -1, never 0
        padded_bytes = payload + [-1] * (8 - dlc)
        data_fields = {f"data_{i}": padded_bytes[i] for i in range(8)}

        if flag == "T":
            attack_type = _map_attack_type(path)
            label = 1
        else:
            attack_type = "normal"
            label = 0

        record = {
            "timestamp": timestamp,
            "can_id": can_id,
            "dlc": dlc,
            **data_fields,
            "is_remote": False,
            "source": "car_hacking",
            "capture": capture_name,
            "attack_type": attack_type,
            "label": label,
            "label_quality": "frame",
        }
        return record, None
