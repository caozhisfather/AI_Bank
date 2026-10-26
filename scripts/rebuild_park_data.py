"""Prepare and explicitly apply a versioned reconstruction of the simulated park."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from carbon_finance.config import DATA_DIR, SCENARIOS
from carbon_finance.data import load_demo_data
from carbon_finance.demo_park import build_park,calibrate_case,write_park,VERSION
from carbon_finance.pipeline import CarbonFinancePipeline
from services.business_store import BusinessStore,encoded,now


def prepare(destination):
    data=build_park()
    training=DATA_DIR/'training_samples.csv'
    if training.exists(): data['training']=pd.read_csv(training)
    else:
        from scripts.generate_demo_data import generate_training
        data['training']=generate_training(np.random.default_rng(42))
    data['external_risks']=pd.DataFrame([dict(scenario=k,driver=v['driver'],change=v['change']) for k,v in SCENARIOS.items()])
    profile=calibrate_case(data,json.loads((DATA_DIR/'reference_case_a.json').read_text(encoding='utf-8')))
    pipeline=CarbonFinancePipeline(data)
    report={'version':VERSION,'subject_count':len(data['companies']),'roles':data['companies'].groupby('business_role').size().to_dict(),'relationship_count':len(data['network']),'case_a':{}}
    for scenario in SCENARIOS:
        result=pipeline.run(scenario)
        assert result['network'].network_risk.between(0,1).all()
        a=result['companies'].set_index('company_id').loc['A']
        report['case_a'][scenario]={k:float(a[k]) for k in ('p_target','data_quality','own_risk','first_order_risk','second_order_risk','network_risk','final_limit')}
    write_park(data,destination)
    if training.exists() and training.resolve()!=(Path(destination)/'training_samples.csv').resolve():
        shutil.copy2(training,Path(destination)/'training_samples.csv')
    path=Path(destination)
    (path/'reference_case_a.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    (path/'reconstruction_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def migrate(store,data,manifest):
    """One SQLite transaction; all old versions, evidence and reference snapshots survive."""
    with store.lock,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS dataset_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, manifest TEXT NOT NULL, previous_reference TEXT NOT NULL)')
        if db.execute('SELECT 1 FROM dataset_migrations WHERE migration_id=?',(VERSION,)).fetchone(): return False
        previous=[dict(row) for row in db.execute('SELECT * FROM business_reference')]
        db.execute('INSERT INTO dataset_migrations VALUES(?,?,?,?)',(VERSION,now(),encoded(manifest),encoded(previous)))
        for key,frame in data.items():
            if isinstance(frame,pd.DataFrame):
                db.execute('INSERT INTO business_reference VALUES(?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload',
                           (key,frame.to_json(orient='records',force_ascii=False,double_precision=15)))
        for company in data['companies'].to_dict('records'):
            cid=company['company_id']
            payload={'company':company,'features':data['features'].loc[data['features'].company_id.eq(cid)].iloc[0].to_dict(),
                     'energy':data['energy'].loc[data['energy'].company_id.eq(cid)].to_dict('records')}
            store._insert_version(db,cid,payload,max(row['period'] for row in payload['energy']),f'{VERSION}业务角色与园区关系重构（模拟）')
    return True


def apply(staging,store=None):
    staging=Path(staging);store=store or BusinessStore();store.seed()
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staging.iterdir()) if p.suffix in ('.csv','.json')}
    with store.connect() as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='dataset_migrations'").fetchone()
        if exists and db.execute('SELECT 1 FROM dataset_migrations WHERE migration_id=?',(VERSION,)).fetchone():
            existing={row[0] for row in db.execute('SELECT name FROM business_reference')}
            optional=('project_history','fund_payments','operating_history')
            missing=[key for key in optional if key not in existing and (staging/f'{key}.csv').exists()]
            if missing:
                previous=[dict(row) for row in db.execute('SELECT * FROM business_reference')]
                db.execute('INSERT INTO dataset_migrations VALUES(?,?,?,?)',(VERSION+'-ledgers',now(),encoded(manifest),encoded(previous)))
                for key in missing:
                    frame=pd.read_csv(staging/f'{key}.csv')
                    db.execute('INSERT INTO business_reference VALUES(?,?)',(key,frame.to_json(orient='records',force_ascii=False,double_precision=15)))
                    shutil.copy2(staging/f'{key}.csv',DATA_DIR/f'{key}.csv')
            return {'applied':False,'added_reference_tables':missing,'reason':'该重构版本已迁移，未覆盖后续业务更新'}
    backup=DATA_DIR/'runtime'/'backups'/f'{VERSION}-{datetime.now():%Y%m%d-%H%M%S}'
    backup.mkdir(parents=True)
    for path in DATA_DIR.iterdir():
        if path.suffix in ('.csv','.json'): shutil.copy2(path,backup/path.name)
    with sqlite3.connect(store.path) as source,sqlite3.connect(backup/'platform.db') as target: source.backup(target)
    data=load_demo_data(staging)
    migrate(store,data,manifest)
    for path in staging.iterdir():
        if path.suffix in ('.csv','.json'):
            temporary=DATA_DIR/(path.name+'.new')
            shutil.copy2(path,temporary);temporary.replace(DATA_DIR/path.name)
    return {'applied':True,'backup':str(backup),'version':VERSION}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--staging',type=Path,default=ROOT/'.codex_tmp'/'park-rebuild-v2')
    args=parser.parse_args()
    report=prepare(args.staging)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.apply: print(json.dumps(apply(args.staging),ensure_ascii=False))
