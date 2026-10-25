"""Base CAN loader interface for STARK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from stark.schema import CANONICAL_COLUMNS, cast_canonical_df
from stark.utils.logging import get_logger

logger = get_logger(__name__)


class BaseCANLoader(ABC):
    """Abstract base class for CAN dataset loaders."""

    @abstractmethod
    def parse_line(
        self,
        line: str,
        capture_name: str,
        path: Path | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a single raw line into a canonical record.

        Args:
            line: Raw line text from the log file.
            capture_name: Identifier for the capture run or file.
            path: Optional source file path for metadata derivation.

        Returns:
            tuple[dict[str, Any] | None, str | None]:
                Tuple of (record_dict, None) on success, or
                (None, rejection_reason) on failure.
        """

    def load_file(
        self,
        path: Path | str,
        capture_name: str | None = None,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """Load and parse an individual CAN log file.

        Args:
            path: Path to the raw CAN dataset file.
            capture_name: Optional custom capture name. Defaults to file stem.

        Returns:
            tuple[pd.DataFrame, dict[str, int]]:
                Tuple of (DataFrame of parsed records, dropped_counts_by_reason).
        """
        file_path = Path(path)
        cap = capture_name if capture_name is not None else file_path.stem
        records: list[dict[str, Any]] = []
        dropped_counts: dict[str, int] = {
            "unparseable": 0,
            "dlc_out_of_range": 0,
            "dlc_mismatch": 0,
            "corrupted": 0,
        }

        logger.info("Loading CAN dataset file: %s (capture: %s)", file_path, cap)
        with file_path.open("r", encoding="utf-8-sig", errors="replace") as f:
            for line_idx, line in enumerate(f):
                line_str = line.strip()
                if not line_str:
                    continue
                record, reason = self.parse_line(line_str, cap, file_path)
                if record is not None:
                    records.append(record)
                else:
                    reason_key = reason if reason in dropped_counts else "corrupted"
                    dropped_counts[reason_key] += 1

        if not records:
            empty_df = pd.DataFrame(columns=CANONICAL_COLUMNS)
            return cast_canonical_df(empty_df), dropped_counts

        raw_df = pd.DataFrame(records)
        canonical_df = cast_canonical_df(raw_df)
        logger.info(
            "Parsed %d valid frames from %s (%d dropped)",
            len(canonical_df),
            file_path.name,
            sum(dropped_counts.values()),
        )
        return canonical_df, dropped_counts

    def load_directory(
        self,
        dir_path: Path | str,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """Load and parse all raw CAN log files within a directory.

        Args:
            dir_path: Directory containing log files.

        Returns:
            tuple[pd.DataFrame, dict[str, int]]:
                Combined parsed DataFrame and aggregated dropped counts.
        """
        root = Path(dir_path)
        files = sorted(
            p
            for p in root.rglob("*")
            if p.is_file()
            and not p.name.startswith(".")
            and p.suffix in {".csv", ".txt", ".log"}
        )
        all_dfs: list[pd.DataFrame] = []
        aggregate_dropped: dict[str, int] = {
            "unparseable": 0,
            "dlc_out_of_range": 0,
            "dlc_mismatch": 0,
            "corrupted": 0,
        }

        for p in files:
            df, dropped = self.load_file(p)
            all_dfs.append(df)
            for k, count in dropped.items():
                aggregate_dropped[k] = aggregate_dropped.get(k, 0) + count

        if not all_dfs:
            empty_df = pd.DataFrame(columns=CANONICAL_COLUMNS)
            return cast_canonical_df(empty_df), aggregate_dropped

        merged = pd.concat(all_dfs, ignore_index=True)
        return cast_canonical_df(merged), aggregate_dropped
