from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA_DIR
from .network import SUPPORT_COLUMNS
from .mitigation import PROFILE_COLUMNS


FILES = {
    "companies": "companies.csv",
    "energy": "energy_performance.csv",
    "features": "transition_features.csv",
    "network": "network_edges.csv",
    "projects": "transition_projects.csv",
    "funds": "fund_usage.csv",
    "external_risks": "external_risks.csv",
    "training": "training_samples.csv",
}


def load_demo_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    missing = [name for name in FILES.values() if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"缺少演示数据：{', '.join(missing)}。请运行 python scripts/generate_demo_data.py"
        )
    data = {key: pd.read_csv(data_dir / filename) for key, filename in FILES.items()}
    if 'reference_case' in data['companies']:
        data['companies']['reference_case'] = data['companies']['reference_case'].fillna('')
    support_path = data_dir / "support_nodes.csv"
    data["support_nodes"] = pd.read_csv(support_path) if support_path.exists() else pd.DataFrame(columns=SUPPORT_COLUMNS)
    data['network_mitigation'] = load_mitigation_profiles(data_dir)
    for key in ('operation_profiles', 'service_history', 'business_flows','project_history','fund_payments','operating_history','water_balance'):
        path = data_dir / f'{key}.csv'
        data[key] = pd.read_csv(path) if path.exists() else pd.DataFrame()
    return data


def load_mitigation_profiles(data_dir: Path = DATA_DIR):
    path = data_dir / 'network_mitigation.csv'
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=PROFILE_COLUMNS)
