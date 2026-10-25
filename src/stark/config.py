"""Configuration and directory paths for STARK."""

from pathlib import Path

# Project root derived dynamically: ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parents[2]

# Data directories
DATA_DIR = ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CAR_HACKING_RAW_DIR = RAW_DATA_DIR / "car_hacking"
OTIDS_RAW_DIR = RAW_DATA_DIR / "otids"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
SAMPLES_DIR = DATA_DIR / "samples"
UPLOADS_DIR = DATA_DIR / "uploads"

# Reports and database
REPORTS_DIR = ROOT / "reports"
DATABASE_PATH = ROOT / "stark.db"

# Global random seed
RANDOM_STATE: int = 42
