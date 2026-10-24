"""OTIDS Dataset loader for STARK."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from stark.data.loaders.base import BaseCANLoader


def _parse_hex_byte(token: str) -> int:
    """Parse a single hex byte string into an int in [0, 255]."""
    tok = token.strip()
    if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,2}", tok):
        raise ValueError(f"Invalid byte token: {token}")
    val = int(tok, 16)
    if val < 0 or val > 255:
        raise ValueError(f"Byte value out of range: {val}")
    return val


def _map_otids_metadata(path: Path | None) -> tuple[str, int, str]:
    """Map OTIDS file path to (attack_type, label, label_quality).

    Design rule:
        label_quality=window for fuzzy and impersonation, frame for DoS.
    """
    if path is None:
        return "unknown", 0, "none"
    stem = path.stem.lower()
    if "dos" in stem:
        return "dos", 1, "frame"
    if "fuzzy" in stem:
        return "fuzzy", 1, "window"
    if "impersonation" in stem:
        return "impersonation", 1, "window"
    if "normal" in stem:
        return "normal", 0, "frame"
    return "normal", 0, "frame"


class OTIDSLoader(BaseCANLoader):
    """Loader for the Oak Ridge National Laboratory OTIDS dataset."""

    def parse_line(
        self,
        line: str,
        capture_name: str,
        path: Path | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a single raw OTIDS line into a canonical record."""
        line_clean = line.strip()
        if not line_clean:
            return None, "unparseable"

        is_remote = bool(re.search(r"\b(remote|rtr)\b", line_clean, re.IGNORECASE))
        attack_type, label, label_quality = _map_otids_metadata(path)

        # Check for tagged text format (e.g. 'Timestamp: ... ID: ... DLC: ...')
        if "timestamp:" in line_clean.lower() or "id:" in line_clean.lower():
            ts_match = re.search(r"timestamp:\s*([0-9.]+)", line_clean, re.IGNORECASE)
            id_match = re.search(r"\bid:\s*([0-9a-fA-F]+)", line_clean, re.IGNORECASE)
            dlc_match = re.search(r"\bdlc:\s*([0-9]+)", line_clean, re.IGNORECASE)

            if not ts_match or not id_match or not dlc_match:
                return None, "unparseable"

            try:
                timestamp = float(ts_match.group(1))
                if not math.isfinite(timestamp) or timestamp < 0:
                    return None, "corrupted"
                can_id = int(id_match.group(1), 16)
                if can_id < 0 or can_id > 0x1FFFFFFF:
                    return None, "corrupted"
                dlc = int(dlc_match.group(1), 10)
            except (ValueError, OverflowError):
                return None, "corrupted"

            if dlc < 0 or dlc > 8:
                return None, "dlc_out_of_range"

            # Extract payload tokens following DLC: <num>
            dlc_pos = dlc_match.end()
            remainder = line_clean[dlc_pos:].strip()
            # Remove any trailing 'Remote' or 'RTR'
            remainder = re.sub(
                r"\b(remote|rtr)\b", "", remainder, flags=re.IGNORECASE
            ).strip()
            tokens = [tok for tok in re.split(r"[\s,]+", remainder) if tok]

            if is_remote:
                # Remote frames have no payload data
                payload = []
            else:
                if len(tokens) != dlc:
                    return None, "dlc_mismatch"
                try:
                    payload = [_parse_hex_byte(tok) for tok in tokens]
                except ValueError:
                    return None, "corrupted"
        else:
            # Delimited format (comma or space separated)
            try:
                fields = [
                    f.strip()
                    for f in next(csv.reader([line_clean], skipinitialspace=True))
                ]
            except (csv.Error, StopIteration):
                fields = line_clean.split()

            if len(fields) == 1 and " " in fields[0]:
                fields = fields[0].split()

            if len(fields) < 3:
                return None, "unparseable"

            try:
                timestamp = float(fields[0])
                if not math.isfinite(timestamp) or timestamp < 0:
                    return None, "corrupted"
                can_id = int(fields[1], 16)
                if can_id < 0 or can_id > 0x1FFFFFFF:
                    return None, "corrupted"
                dlc = int(fields[2], 10)
            except (ValueError, OverflowError):
                return None, "corrupted"

            if dlc < 0 or dlc > 8:
                return None, "dlc_out_of_range"

            raw_tokens = fields[3:]
            payload_tokens = [
                tok
                for tok in raw_tokens
                if not re.match(r"^(remote|rtr)$", tok, re.IGNORECASE)
            ]

            if is_remote:
                payload = []
            else:
                if len(payload_tokens) != dlc:
                    return None, "dlc_mismatch"
                try:
                    payload = [_parse_hex_byte(tok) for tok in payload_tokens]
                except ValueError:
                    return None, "corrupted"

        padded_bytes = payload + [-1] * (8 - dlc)
        data_fields = {f"data_{i}": padded_bytes[i] for i in range(8)}

        record = {
            "timestamp": timestamp,
            "can_id": can_id,
            "dlc": dlc,
            **data_fields,
            "is_remote": is_remote,
            "source": "otids",
            "capture": capture_name,
            "attack_type": attack_type,
            "label": label,
            "label_quality": label_quality,
        }
        return record, None
