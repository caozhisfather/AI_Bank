"""Reproducible inputs for the explicitly simulated plan-A reference case."""
import csv
import json

from .config import DATA_DIR


def apply_reference_case_files(data_dir=DATA_DIR):
    profile_path = data_dir / 'reference_case_a.json'
    if not profile_path.exists():
        return
    profile = json.loads(profile_path.read_text())

    def update(filename, changes, defaults=None):
        path = data_dir / filename
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, rows = list(reader.fieldnames), list(reader)
        defaults = defaults or {}
        for field in changes:
            if field not in fields:
                fields.append(field)
                for row in rows:
                    row[field] = defaults[field](row) if callable(defaults.get(field)) else defaults.get(field, '')
        for row in rows:
            if row['company_id'] == 'A':
                row.update(changes)
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows(rows)

    features = profile['features']
    update('transition_features.csv', features, {'direct_shock_sensitivity': lambda row: row['shock_sensitivity']})
    update('companies.csv', {'base_limit': 3000, 'project_need': 1000,
                            'shock_sensitivity': features['shock_sensitivity'],
                            'reference_case': profile['case_id'], 'reference_finance_rounding': 1,
                            'reference_finance_params': json.dumps(profile.get('finance_params',{}),ensure_ascii=False)},
           {'reference_finance_rounding': 0, 'reference_finance_params':'{}'})
    update('transition_projects.csv', {'project_progress': features['project_progress']})
    path = data_dir / 'network_mitigation.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = list(reader.fieldnames), list(reader)
    for row in rows:
        if row['target'] == 'A':
            row.update(profile['incoming_protection'])
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
