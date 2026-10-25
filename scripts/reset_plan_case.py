"""Explicit reset of the simulated A case; preserve every earlier data version."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from carbon_finance.data import load_demo_data
from services.business_store import BusinessStore, encoded


def reset_case(store):
    data = load_demo_data()
    store.seed()
    payload = {
        'company': data['companies'].loc[data['companies'].company_id == 'A'].iloc[0].to_dict(),
        'features': data['features'].loc[data['features'].company_id == 'A'].iloc[0].to_dict(),
        'energy': data['energy'].loc[data['energy'].company_id == 'A'].to_dict('records'),
    }
    with store.lock, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = store.latest('A')
        if encoded(previous['payload']) != encoded(payload):
            store._insert_version(db, 'A', payload, max(r['period'] for r in payload['energy']),
                                  '策划书企业A演示案例重设v1（模拟）')
        profiles = data['network_mitigation'].to_json(orient='records', force_ascii=False, double_precision=15)
        db.execute('INSERT INTO business_reference VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload',
                   ('network_mitigation', profiles))
        previous_projects = db.execute("SELECT payload FROM business_reference WHERE name='projects'").fetchone()
        if previous_projects:
            projects = json.loads(previous_projects[0])
            replacement = data['projects'].loc[data['projects'].company_id == 'A'].iloc[0].to_dict()
            db.execute("UPDATE business_reference SET payload=? WHERE name='projects'",
                       (encoded([replacement if row['company_id']=='A' else row for row in projects]),))
    return store.latest('A')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Create a new version of the explicitly simulated A case')
    args = parser.parse_args()
    if not args.apply:
        parser.exit(message='Pass --apply to reset only the simulated A case; previous versions are retained.\n')
    latest = reset_case(BusinessStore())
    print(f"企业A模拟案例已更新至 V{latest['version']}；历史版本保留。")
