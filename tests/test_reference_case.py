import copy

import pytest

from carbon_finance.pipeline import CarbonFinancePipeline
from scripts.reset_plan_case import reset_case


def test_plan_a_normal_relief_and_gas_stress_are_calculated_from_inputs():
    pipeline=CarbonFinancePipeline()
    normal=pipeline.run('正常情景')['companies'].set_index('company_id').loc['A']
    stress=pipeline.run('天然气价格上涨30%')['companies'].set_index('company_id').loc['A']
    assert normal.p_target==pytest.approx(.826,abs=.0005)
    assert stress.p_target==pytest.approx(.740,abs=.0005)
    assert normal.data_quality==pytest.approx(.95)
    assert stress.data_quality==pytest.approx(normal.data_quality)
    assert normal.own_risk==pytest.approx(1-normal.p_target)
    assert stress.own_risk==pytest.approx(1-stress.p_target)
    assert normal.network_risk==pytest.approx(.16)
    assert stress.network_risk==pytest.approx(.31)
    assert normal.first_order_risk<0
    assert normal.first_order_risk+normal.second_order_risk == pytest.approx(.16-normal.own_risk)
    assert stress.first_order_risk>0 and stress.second_order_risk>0
    for row in [normal,stress]:
        assert row.network_risk==pytest.approx(row.own_risk+row.first_order_risk+row.second_order_risk)
    assert [normal.transition_support,normal.network_deduction,normal.final_limit]==[628,116,3512]
    assert [stress.transition_support,stress.network_deduction,stress.final_limit]==[562,221,3341]
    assert normal.suggested_rate==pytest.approx(.037)
    assert normal.raroc==pytest.approx(.091)
    assert normal.warning_level.startswith('绿色')
    assert stress.warning_level.startswith('橙色')
    # No A-specific output override: changing its filed facts changes the prediction and risk.
    pipeline.data['features'].loc[pipeline.data['features'].company_id=='A','project_progress']=.2
    changed=pipeline.run('正常情景')['companies'].set_index('company_id').loc['A']
    assert changed.p_target!=normal.p_target
    assert changed.network_risk!=normal.network_risk


def test_reference_reset_preserves_versions_and_other_companies(isolated_platform):
    store=isolated_platform
    store.seed()
    before=store.latest('A')
    other=copy.deepcopy(store.latest('B'))
    altered=copy.deepcopy(before['payload'])
    altered['features']['project_progress']=.2
    with store.connect() as db:
        store._insert_version(db,'A',altered,before['period'],'测试历史版本')
    reset=reset_case(store)
    assert reset['version']==before['version']+2
    assert reset['payload']['features']==before['payload']['features']
    assert store.latest('B')==other
    assert reset_case(store)['id']==reset['id']
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM company_versions WHERE company_id='A'").fetchone()[0]==3
