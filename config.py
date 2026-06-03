import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_START = "20240101"
DEFAULT_END = "20261231"

GRID_CONFIG = {
    "起投金额": 10000,
    "回测天数": 60,
    "止损比例": 0.05,
    "止盈比例": 0.10,
}
