from pathlib import Path
import shutil
import sqlite3

import pandas as pd
import pytest

from carbon_finance.config import DATA_DIR
from services.backend_import import import_snapshot
from services.business_store import BusinessStore


@pytest.fixture
def snapshot_dir(tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    for source in DATA_DIR.glob("*.csv"):
        shutil.copy2(source, folder / source.name)
    return folder


def test_default_import_only_validates_and_creates_no_target_database(snapshot_dir, tmp_path):
    database = tmp_path / "untouched.db"
    result = import_snapshot(snapshot_dir, database, "测试场景验证数据")
    assert result["applied"] is False
    assert result["mode"] == "validation_only"
    assert result["company_count"] > 0
    assert not database.exists()


def test_apply_is_versioned_backed_up_and_idempotent(snapshot_dir, isolated_platform):
    isolated_platform.seed()
    before = isolated_platform.latest("A")
    result = import_snapshot(snapshot_dir, isolated_platform.path, "测试后台业务快照", apply=True)
    assert result["applied"] is True
    current = isolated_platform.latest("A")
    assert current["version"] == before["version"] + 1
    assert result["batch_id"] in current["source"]
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT COUNT(*) FROM company_versions").fetchone()[0] > 0
    repeated = import_snapshot(snapshot_dir, isolated_platform.path, "测试后台业务快照", apply=True)
    assert repeated["applied"] is False
    assert repeated["batch_id"] == result["batch_id"]
    assert isolated_platform.latest("A")["id"] == current["id"]


def test_invalid_network_is_rejected_before_any_write(snapshot_dir, isolated_platform):
    isolated_platform.seed()
    before = isolated_platform.latest("A")["id"]
    network_path = snapshot_dir / "network_edges.csv"
    network = pd.read_csv(network_path)
    network.loc[0, "target"] = "UNKNOWN-ENDPOINT"
    network.to_csv(network_path, index=False)
    with pytest.raises(ValueError, match="未登记"):
        import_snapshot(snapshot_dir, isolated_platform.path, "错误关系快照", apply=True)
    assert isolated_platform.latest("A")["id"] == before
