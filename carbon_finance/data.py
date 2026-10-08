from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA_DIR


FILES = {
    "companies": "companies.csv",
    "energy": "energy_performance.csv",
    "features": "transition_features.csv",
    "network": "network_edges.csv",
    "training": "training_samples.csv",
}


def load_demo_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    missing = [name for name in FILES.values() if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"缺少演示数据：{', '.join(missing)}。请运行 python scripts/generate_demo_data.py"
        )
    return {key: pd.read_csv(data_dir / filename) for key, filename in FILES.items()}
