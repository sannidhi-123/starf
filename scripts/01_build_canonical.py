"""CLI script to build canonical Parquet datasets from raw CAN files."""

from __future__ import annotations

import argparse
from pathlib import Path

from stark.config import PROCESSED_DATA_DIR
from stark.data.clean import clean_canonical_df
from stark.data.loaders.car_hacking import CarHackingLoader
from stark.data.loaders.otids import OTIDSLoader
from stark.schema import validate
from stark.utils.logging import get_logger

logger = get_logger("01_build_canonical")


def main() -> None:
    """Parse raw CAN files and save validated canonical Parquet."""
    parser = argparse.ArgumentParser(
        description="Build canonical Parquet dataset from raw Car-Hacking or OTIDS logs."
    )
    parser.add_argument(
        "--source",
        choices=["car_hacking", "otids"],
        required=True,
        help="Source format of the raw dataset: 'car_hacking' or 'otids'",
    )
    parser.add_argument(
        "--raw",
        type=str,
        required=True,
        help="Path to raw dataset file or directory",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Destination path for output Parquet file (defaults to data/processed/{source}_canonical.parquet)",
    )
    args = parser.parse_args()

    raw_path = Path(args.raw)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw dataset path does not exist: {raw_path}")

    loader = CarHackingLoader() if args.source == "car_hacking" else OTIDSLoader()

    if raw_path.is_file():
        parsed_df, parse_dropped = loader.load_file(raw_path)
    else:
        parsed_df, parse_dropped = loader.load_directory(raw_path)

    cleaned_df, report = clean_canonical_df(parsed_df)
    validate(cleaned_df)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = PROCESSED_DATA_DIR / f"{args.source}_canonical.parquet"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_df.to_parquet(out_path, index=False)

    print(
        f"Successfully built canonical dataset for '{args.source}':\n"
        f"  Input rows:      {report.rows_in}\n"
        f"  Output rows:     {report.rows_out}\n"
        f"  Parse dropped:   {parse_dropped}\n"
        f"  Clean dropped:   {report.dropped_per_reason}\n"
        f"  Saved to:        {out_path}"
    )


if __name__ == "__main__":
    main()
