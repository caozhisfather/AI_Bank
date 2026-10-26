"""Validate and import business CSV snapshots from an administrative terminal."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.backend_import import import_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path, help="包含业务 CSV 表的目录")
    parser.add_argument("--source-label", required=True, help="如实记录数据来源和用途")
    parser.add_argument("--database", type=Path, default=ROOT / "data/runtime/platform.db")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="校验通过后备份并版本化入库；默认只校验")
    args = parser.parse_args()
    try:
        result = import_snapshot(args.source_dir, args.database, args.source_label,
                                 apply=args.apply, backup_dir=args.backup_dir)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        parser.exit(1, f"导入未执行：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
