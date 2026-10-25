import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from carbon_finance.config import DATA_DIR
from carbon_finance.data import load_demo_data
from carbon_finance.demo_park import build_park
from carbon_finance.pipeline import CarbonFinancePipeline
from carbon_finance.lmdi import decompose_lmdi
from scripts.rebuild_park_data import migrate


def test_subject_roles_names_and_utility_directions_match_business():
    data=build_park()
    companies=data['companies'].set_index('company_id')
    assert len(companies)==36
    assert companies.company_name.nunique()==36
    assert not companies.company_name.str.contains(r'\d').any()
    assert companies.groupby('business_role').size().to_dict()=={'steel':12,'materials':7,'supplier':6,'customer':5,'energy':3,'infra':3}
    for edge in data['network'].itertuples():
        if edge.dependency_class=='infra': assert companies.loc[edge.source,'node_type']=='infra'
        if edge.dependency_class=='energy': assert companies.loc[edge.source,'node_type']=='energy' or edge.commodity=='回收余热'
        assert edge.weight==pytest.approx(edge.share*edge.criticality)
        assert edge.commodity and edge.direction_basis and '模拟' in edge.evidence_status
    assert companies.loc['P15','node_type']=='enterprise'  # Oxygen/nitrogen is a process input, not fuel gas.
    assert not companies.loc[['P12','P20'],'in_park'].any()


def test_monthly_flows_reconcile_service_capacity_and_purchase_sales_references():
    data=build_park(); flows=data['business_flows']; edges=data['network']
    assert not flows.duplicated(['provider_id','customer_id','commodity','period']).any()
    for edge in edges.itertuples():
        seller,buyer=(edge.target,edge.source) if edge.relation_type=='销售依赖' else (edge.source,edge.target)
        selected=flows.loc[(flows.provider_id==seller)&(flows.customer_id==buyer)&(flows.commodity==edge.commodity)]
        assert len(selected)==12
        assert selected.quantity.sum()==pytest.approx(edge.annualized_quantity)
    history=data['service_history']
    for row in history.loc[history.company_id.isin(['D','P26','P27','P28','P29','P30'])].itertuples():
        selected=flows.loc[(flows.provider_id==row.company_id)&(flows.period==row.period)]
        if row.company_id=='P29': selected=selected.loc[selected.commodity=='污水处理']
        assert row.quantity==pytest.approx(selected.quantity.sum())
        assert row.quantity<=row.capacity
        if row.company_id=='P29': assert row.reclaimed_water_output<=row.quantity
    balance=data['water_balance']
    assert balance.water_supplied.to_numpy()==pytest.approx((balance.fresh_water+balance.reclaimed_water).to_numpy())
    assert balance.wastewater_received.to_numpy()==pytest.approx((balance.treated_water_discharged+balance.reclaimed_water).to_numpy())
    assert (balance.treated_water_discharged>=0).all()


def test_a_energy_inputs_reproduce_plan_example_and_features():
    data=load_demo_data()
    frame=data['energy'].loc[data['energy'].company_id=='A']
    periods=sorted(frame.period.unique())
    result=decompose_lmdi(frame.loc[frame.period.isin([periods[0],periods[-1]])])
    assert [result[k] for k in ['activity','efficiency','energy_structure','total_change']]==pytest.approx([2000,-9000,-5000,-12000])
    feature=data['features'].set_index('company_id').loc['A']
    assert feature.lmdi_efficiency_share==pytest.approx(9/14)
    assert feature.lmdi_energy_share==pytest.approx(5/14)
    assert not result['process_available'] and result['process'] is None


def test_model_business_features_reconcile_to_project_payment_and_cash_ledgers():
    data=load_demo_data()
    for feature in data['features'].loc[data['features'].evaluation_model.eq('transition')].itertuples():
        project=data['project_history'].loc[data['project_history'].company_id.eq(feature.company_id)].sort_values('period').iloc[-1]
        payments=data['fund_payments'].loc[data['fund_payments'].company_id.eq(feature.company_id)]
        cash=data['operating_history'].loc[data['operating_history'].company_id.eq(feature.company_id)]
        assert project.actual_progress==pytest.approx(feature.project_progress)
        assert project.own_fund_received/project.own_fund_plan==pytest.approx(feature.own_fund_arrival)
        assert payments.loc[payments.rule_matched,'amount'].sum()/payments.amount.sum()==pytest.approx(feature.fund_usage_match)
        assert cash.operating_cashflow.sum()/cash.debt_service.sum()==pytest.approx(feature.cashflow_coverage)
        assert cash.energy_expense.sum()/cash.operating_cost.sum()==pytest.approx(feature.energy_cost_ratio)
        assert not payments.bank_verified.any()


def test_operating_nodes_have_no_transition_predictions_or_financing(bank_headers):
    with TestClient(app) as client:
        for cid in ['D','P29','P20']:
            response=client.get(f'/api/v1/companies/{cid}/analysis',headers=bank_headers)
            assert response.status_code==200,response.text
            result=response.json(); company=result['company']
            assert company['evaluation_model']=='operating'
            assert company['p_target'] is None and company['final_limit'] is None
            assert result['lmdi'] is None and result['shap_probability'] is None
            assert result['service_history']
            assert result['network_graph']['nodes']
        assert client.get('/api/v1/companies/D/agent-workflow',headers=bank_headers).status_code==400


def test_migration_is_idempotent_and_retains_old_identity_and_reference(isolated_platform):
    store=isolated_platform;store.seed()
    before=copy.deepcopy(store.latest('D'))
    data=load_demo_data()
    altered=copy.deepcopy(data)
    altered['companies'].loc[altered['companies'].company_id=='D','company_name']='版本迁移验证燃气公司'
    assert migrate(store,altered,{'test':'snapshot'})
    assert store.latest('D')['version']==before['version']+1
    with store.connect() as db:
        historical=json.loads(db.execute('SELECT payload FROM company_versions WHERE id=?',(before['id'],)).fetchone()[0])
        assert historical==before['payload']
        assert json.loads(db.execute('SELECT previous_reference FROM dataset_migrations').fetchone()[0])
    assert not migrate(store,altered,{'test':'snapshot'})
    assert store.latest('D')['version']==before['version']+1


def test_utility_pressure_follows_its_actual_exposure():
    pipeline=CarbonFinancePipeline()
    normal=pipeline.run()['network'].set_index('company_id')
    gas=pipeline.run('天然气价格上涨30%')['network'].set_index('company_id')
    electricity=pipeline.run('电价上涨20%')['network'].set_index('company_id')
    assert gas.loc['P27','own_risk']-normal.loc['P27','own_risk']>gas.loc['P29','own_risk']-normal.loc['P29','own_risk']
    assert electricity.loc['P29','own_risk']-normal.loc['P29','own_risk']>gas.loc['P29','own_risk']-normal.loc['P29','own_risk']
