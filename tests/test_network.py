import pandas as pd
import pytest

from carbon_finance.network import affected_credit_exposure, propagate_risk
from carbon_finance.mitigation import apply_mitigation_profiles, PROFILE_COLUMNS


def test_signed_net_terms_can_reproduce_plan_relief_without_negative_dependency_weights():
    nodes=pd.DataFrame([['A','企业A',.174],['B','企业B',.1],['U','企业U',0]],columns=['company_id','company_name','initial_risk'])
    edges=pd.DataFrame([['B','A',.4,'采购依赖'],['U','B',.4,'能源依赖']],columns=['source','target','weight','relation_type'])
    profiles=pd.DataFrame([
        ['B','A','采购依赖',.15,1.,1.,1.,'备用供应（模拟）','测试参数','2025-12','模拟参数'],
        ['U','B','能源依赖',2/3,1.,1.,1.,'备用能源（模拟）','测试参数','2025-12','模拟参数'],
    ],columns=PROFILE_COLUMNS)
    enriched=apply_mitigation_profiles(edges,profiles)
    result,paths=propagate_risk(nodes,enriched,decay=.5,max_paths=None)
    a=result.set_index('company_id').loc['A']
    assert (enriched.weight>=0).all()
    assert a.first_order_risk==pytest.approx(-.01)
    assert a.second_order_risk==pytest.approx(-.004)
    assert a.network_risk==pytest.approx(.16)
    for order,field in [(1,'first_order_risk'),(2,'second_order_risk')]:
        assert sum(p['contribution'] for p in paths['A'] if p['order']==order)==pytest.approx(a[field])
    assert all(p['contribution']==pytest.approx(p['gross_contribution']-p['mitigation_contribution']) for p in paths['A'])
    stressed,_=propagate_risk(nodes.assign(initial_risk=[.26,.3,.4]),apply_mitigation_profiles(edges,profiles,shock=.3),decay=.5)
    stress=stressed.set_index('company_id').loc['A']
    assert stress.first_order_risk>0 and stress.second_order_risk>0
    assert stress.network_risk>a.network_risk
    missing,_=propagate_risk(nodes,apply_mitigation_profiles(edges,profiles.iloc[:1]),decay=.5)
    assert missing.set_index('company_id').loc['A','second_order_mitigation']==0
    capped,_=propagate_risk(nodes.assign(initial_risk=0),enriched,decay=1)
    assert capped.network_risk.min()==0
    with pytest.raises(ValueError,match='来源'):
        apply_mitigation_profiles(edges,profiles.assign(data_source=''))
    with pytest.raises(ValueError,match='有限数值'):
        apply_mitigation_profiles(edges,profiles.assign(effectiveness=1.2))


def test_two_order_propagation_follows_edge_direction():
    nodes = pd.DataFrame(
        [["A", "A企业", 0.5], ["B", "B企业", 0.1], ["C", "C企业", 0.1]],
        columns=["company_id", "company_name", "initial_risk"],
    )
    edges = pd.DataFrame(
        [["A", "B", 0.6], ["B", "C", 0.5]],
        columns=["source", "target", "weight"],
    )
    result, paths = propagate_risk(nodes, edges, decay=0.5)
    indexed = result.set_index("company_id")
    assert indexed.loc["B", "first_order_risk"] > 0
    assert indexed.loc["C", "second_order_risk"] > 0
    assert paths["C"][0]["path"] == "A -> B -> C"


def test_credit_exposure_counts_directed_two_hop_companies_once():
    companies = pd.DataFrame(
        [[key, f"{key}企业", "钢铁", amount] for key, amount in zip("ABCDE", [1000, 2000, 3000, 4000, 5000])],
        columns=["company_id", "company_name", "industry", "base_limit"],
    )
    edges = pd.DataFrame(
        [["A", "B", 0.6], ["A", "B", 0.1], ["B", "C", 0.5],
         ["C", "A", 0.2], ["A", "C", 0.2], ["C", "D", 0.4],
         ["D", "E", 0.4], ["E", "A", 0.3], ["A", "E", 0.0], ["A", "UNKNOWN", 0.5]],
        columns=["source", "target", "weight"],
    )
    result = affected_credit_exposure(companies, edges, "A")
    assert result["total_exposure"] == 10000
    assert result["own_exposure"] == 1000
    assert result["first_order_exposure"] == 5000
    assert result["second_order_exposure"] == 4000
    assert result["company_count"] == 4
    assert result["park_total_exposure"] == 15000
    assert result["exposure_share"] == pytest.approx(2 / 3)
    orders = {item["company_id"]: item["propagation_order"] for item in result["companies"]}
    assert orders == {"A": 0, "B": 1, "C": 1, "D": 2}


def test_credit_exposure_handles_isolated_zero_credit_company():
    companies = pd.DataFrame(
        [["A", "A企业", "钢铁", 0]],
        columns=["company_id", "company_name", "industry", "base_limit"],
    )
    edges = pd.DataFrame(columns=["source", "target", "weight"])
    result = affected_credit_exposure(companies, edges, "A")
    assert result["company_count"] == 1
    assert result["total_exposure"] == 0
    assert result["exposure_share"] == 0
    with pytest.raises(KeyError):
        affected_credit_exposure(companies, edges, "UNKNOWN")


def test_three_relation_layers_and_path_values_share_normalized_weights():
    from carbon_finance.network import prepare_network
    nodes = pd.DataFrame([['A', 'A', .4], ['B', 'B', .2], ['C', 'C', .1]], columns=['company_id', 'company_name', 'initial_risk'])
    edges = pd.DataFrame([
        ['A', 'C', .8, '采购依赖'], ['A', 'C', .6, '能源依赖'],
        ['B', 'C', .9, '公共设施依赖'], ['C', 'A', .4, '销售依赖'],
    ], columns=['source', 'target', 'weight', 'relation_type'])
    weights = {'supply': .5, 'energy': 1, 'infra': 1}
    prepared = prepare_network(nodes, edges, relation_weights=weights)
    assert prepared['layers']['supply'][2, 0] == .8
    assert prepared['layers']['energy'][2, 0] == .6
    assert prepared['layers']['infra'][2, 1] == .9
    assert prepared['matrix'][2, 0] == pytest.approx(1 / 1.9)
    assert prepared['matrix'][2, 1] == pytest.approx(.9 / 1.9)
    result, paths = propagate_risk(nodes, edges, decay=.5, relation_weights=weights, max_paths=None)
    by_id = result.set_index('company_id')
    for node_id in nodes.company_id:
        assert sum(p['contribution'] for p in paths[node_id] if p['order'] == 1) == pytest.approx(by_id.loc[node_id, 'first_order_risk'])
        assert sum(p['contribution'] for p in paths[node_id] if p['order'] == 2) == pytest.approx(by_id.loc[node_id, 'second_order_risk'])
    ac = next(p for p in paths['C'] if p['path'] == 'A -> C')
    assert len(ac['segments'][0]['channels']) == 2  # Neither parallel category is overwritten.
    assert ac['contribution'] == pytest.approx(.5 * (1 / 1.9) * .4)
    assert any(p['path'] == 'C -> A -> C' for p in paths['C'])  # Same feedback paths as W squared.


def test_ambiguous_shared_sources_and_logistics_are_preserved_but_excluded():
    from carbon_finance.network import normalize_relations
    edges = pd.DataFrame([
        ['A', 'B', .5, '共享能源'], ['A', 'C', .3, '物流依赖'],
        ['A', 'D', .4, '公共工程依赖'], ['A', 'E', .2, '供应依赖'],
        ['A', 'F', .1, '客户依赖'], ['A', 'G', .6, '能源依赖'],
    ], columns=['source', 'target', 'weight', 'relation_type'])
    relations = normalize_relations(edges, set('ABCDEFG'))
    assert len(relations) == 6
    assert len(relations.loc[relations.active]) == 4
    assert set(relations.loc[~relations.active].original_relation_type) == {'共享能源', '物流依赖'}
    companies = pd.DataFrame([[key, key, '钢铁', 100] for key in 'ABCDEFG'], columns=['company_id', 'company_name', 'industry', 'base_limit'])
    exposure = affected_credit_exposure(companies, edges, 'A')
    assert {item['company_id'] for item in exposure['companies']} == set('ADEFG')
    # An explicit declaration with direction evidence can resolve a former shared-source record.
    declared = edges.iloc[:1].copy()
    declared['dependency_class'] = 'energy'
    declared['direction_basis'] = '已核验供能合同明确A为供给方、B为用能方'
    assert normalize_relations(declared, set('AB')).iloc[0].active


def test_support_nodes_need_evidence_and_can_transmit_without_inventing_credit():
    from carbon_finance.network import support_risk_nodes
    support = pd.DataFrame([['U', '园区污水处理设施', 'infra', .3, '运行核验记录', '2026-10']],
                           columns=['node_id', 'node_name', 'node_type', 'initial_risk', 'risk_source', 'reporting_period'])
    companies = pd.DataFrame([['A', 'A', '钢铁', 100], ['B', 'B', '水泥', 200]], columns=['company_id', 'company_name', 'industry', 'base_limit'])
    edges = pd.DataFrame([['A', 'U', .5, '采购依赖'], ['U', 'B', .8, '公共设施依赖']], columns=['source', 'target', 'weight', 'relation_type'])
    exposure = affected_credit_exposure(companies, edges, 'A', support_nodes=support)
    assert exposure['total_exposure'] == 300
    assert exposure['company_count'] == 2
    assert exposure['first_order_exposure'] == 0
    assert exposure['second_order_exposure'] == 200
    nodes = pd.concat([pd.DataFrame([['A', 'A', .4], ['B', 'B', .1]], columns=['company_id', 'company_name', 'initial_risk']), support_risk_nodes(support, set('AB'))], ignore_index=True)
    risk, _ = propagate_risk(nodes, edges)
    assert risk.set_index('company_id').loc['B', 'first_order_risk'] == pytest.approx(.55 * .8 * .3)
    with pytest.raises(ValueError, match='风险来源'):
        support_risk_nodes(support.assign(risk_source=''), set('AB'))
    with pytest.raises(ValueError, match='编号须唯一'):
        support_risk_nodes(support.assign(node_id='A'), set('AB'))


def test_disabled_relation_class_is_excluded_from_paths_and_credit_scope():
    companies = pd.DataFrame([['A', 'A', '钢铁', 100], ['B', 'B', '水泥', 200]], columns=['company_id', 'company_name', 'industry', 'base_limit'])
    edges = pd.DataFrame([['A', 'B', .7, '能源依赖']], columns=['source', 'target', 'weight', 'relation_type'])
    weights = {'energy': 0}
    assert affected_credit_exposure(companies, edges, 'A', relation_weights=weights)['total_exposure'] == 100
    nodes = companies[['company_id', 'company_name']].assign(initial_risk=[.4, .1])
    result, paths = propagate_risk(nodes, edges, relation_weights=weights)
    assert paths['B'] == []
    assert result.set_index('company_id').loc['B', 'network_risk'] == .1


def test_purchase_and_sales_follow_influencer_to_dependent_without_auto_reversing():
    from carbon_finance.network import normalize_relations
    nodes = pd.DataFrame([['SUPPLIER', '供应商', .6], ['CUSTOMER', '客户', .4], ['FIRM', '企业', 0]],
                         columns=['company_id', 'company_name', 'initial_risk'])
    edges = pd.DataFrame([['SUPPLIER', 'FIRM', .5, '采购依赖'], ['CUSTOMER', 'FIRM', .8, '销售依赖']],
                         columns=['source', 'target', 'weight', 'relation_type'])
    relations = normalize_relations(edges)
    assert set(relations.direction_basis) == {'演示方向，业务角色待核验'}
    risk, paths = propagate_risk(nodes, edges, decay=.5)
    assert risk.set_index('company_id').loc['FIRM', 'first_order_risk'] == pytest.approx(.5 * (.5 * .6 + .8 * .4) / 1.3)
    assert paths['SUPPLIER'] == []
    assert paths['CUSTOMER'] == []


def test_comprehensive_risk_sums_already_decayed_terms_and_caps_at_one():
    nodes = pd.DataFrame([['A','A',.6],['B','B',.4],['C','C',.3]],columns=['company_id','company_name','initial_risk'])
    edges = pd.DataFrame([['A','B',.5],['B','C',.5]],columns=['source','target','weight'])
    result, _ = propagate_risk(nodes,edges,decay=.5)
    c = result.set_index('company_id').loc['C']
    assert c.first_order_risk == pytest.approx(.1)
    assert c.second_order_risk == pytest.approx(.0375)
    assert c.network_risk == pytest.approx(.4375)
    capped, _ = propagate_risk(nodes.assign(initial_risk=[.9,.9,.9]),edges,decay=1)
    assert capped.set_index('company_id').loc['C','network_risk'] == 1
