import pandas as pd
import pytest
from carbon_finance.network import prepare_network, propagate_risk
from services.network_analysis import explain_network


def test_network_explanation_separates_current_source_contribution_from_global_shock():
    nodes = pd.DataFrame([['A','企业A',.2],['B','企业B',.3],['C','企业C',.1],['U','企业U',.4]],columns=['company_id','company_name','initial_risk'])
    edges = pd.DataFrame([['A','B',.6,'采购依赖'],['B','C',.5,'销售依赖'],['U','B',.2,'能源依赖'],['C','A',.4,'公共设施依赖']],columns=['source','target','weight','relation_type'])
    normal,_=propagate_risk(nodes,edges)
    selected_nodes=nodes.assign(initial_risk=[.4,.3,.1,.7])
    selected,_=propagate_risk(selected_nodes,edges)
    prepared=prepare_network(nodes,edges)
    result=explain_network('A',selected,normal,prepared)
    assert all(item['node_ids'][-1]=='A' for item in result['incoming_paths'])
    assert all(item['node_ids'][0]=='A' for item in result['outgoing_paths'])
    a=selected.set_index('company_id').loc['A']
    assert sum(p['contribution'] for p in result['incoming_paths'] if p['order']==1)==pytest.approx(a.first_order_risk)
    assert sum(p['contribution'] for p in result['incoming_paths'] if p['order']==2)==pytest.approx(a.second_order_risk)
    b=next(item for item in result['recipients'] if item['company_id']=='B')
    assert b['delta']==pytest.approx(.55*.6*.2)
    assert b['risk_delta']==pytest.approx(.55*(.6*.2+.2*.3))
    c=next(item for item in result['recipients'] if item['company_id']=='C')
    assert c['delta']==pytest.approx(.55**2*.5*.6*.2)
    assert c['risk_delta']>c['delta']
    unchanged=explain_network('A',normal,normal,prepared)
    assert all(p['delta']==0 for p in unchanged['incoming_paths']+unchanged['outgoing_paths'])
