from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

RELATION_CLASSES = {
    'supply': {'label': '采购/销售依赖', 'color': '#477ba6', 'dash': ''},
    'energy': {'label': '能源依赖', 'color': '#8a67a8', 'dash': '9 5'},
    'infra': {'label': '公共设施依赖', 'color': '#678f89', 'dash': '2 5'},
}
RELATION_ALIASES = {
    '采购依赖': ('supply', '采购依赖'), '供应依赖': ('supply', '采购依赖'),
    '销售依赖': ('supply', '销售依赖'), '客户依赖': ('supply', '销售依赖'),
    '能源依赖': ('energy', '能源依赖'),
    '公共设施依赖': ('infra', '公共设施依赖'), '公共工程依赖': ('infra', '公共设施依赖'),
}
SUPPORT_COLUMNS = ['node_id', 'node_name', 'node_type', 'initial_risk', 'risk_source', 'reporting_period']


def relation_coefficients(values: dict | None = None) -> dict:
    result = {key: 1.0 for key in RELATION_CLASSES}
    if values:
        if set(values) - result.keys():
            raise ValueError('未知的关系类别权重')
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('关系类别权重须为 0–1 之间的有限数值')
            result[key] = float(value)
    return result


def normalize_relations(edges: pd.DataFrame, known_ids: set | None = None) -> pd.DataFrame:
    """Keep source records; quarantine ambiguous channels instead of inventing directions."""
    business_fields = ['commodity','share','share_basis','criticality','replacement_days','inventory_days','annualized_quantity','quantity_unit']
    columns = business_fields + ['relation_id', 'source', 'target', 'weight', 'dependency_class', 'relation_type',
               'original_relation_type', 'data_source', 'reporting_period', 'evidence_status', 'direction_basis', 'active', 'pending_reason',
               'mitigation_capacity', 'mitigation_mechanism', 'mitigation_source', 'mitigation_status', 'mitigation_period']
    rows = []
    for index, row in enumerate(edges.to_dict(orient='records')):
        source, target = row.get('source'), row.get('target')
        original = str(row.get('relation_type', '') or '').strip()
        category, subtype = RELATION_ALIASES.get(original, (None, original))
        declared = row.get('dependency_class')
        if declared in RELATION_CLASSES and row.get('direction_basis'):
            category = declared
        # Compatibility for algorithm clients with untyped three-column edge lists.
        if not original and not declared:
            category, subtype = 'supply', '业务依赖'
        reasons = []
        if category is None:
            reasons.append('共享来源或物流服务关系缺少明确供给方、依赖对象及方向依据' if original in ('共享能源', '物流依赖') else '关系类别或方向依据未明确')
        value = row.get('weight')
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1
        if not valid:
            reasons.append('依赖强度须为 0–1 的有限数值')
        if not source or not target or source == target:
            reasons.append('关系端点为空或属于自环')
        if known_ids is not None and (source not in known_ids or target not in known_ids):
            reasons.append('关系端点缺少企业或公共支撑节点资料')
        capacity = row.get('mitigation_capacity', 0)
        if isinstance(capacity, bool) or not isinstance(capacity, (int, float)) or not math.isfinite(capacity) or not 0 <= capacity <= 1:
            raise ValueError('缓释能力须为 0–1 的有限数值')
        if capacity and any(not isinstance(row.get(field), str) or not row[field].strip()
                            for field in ('mitigation_mechanism', 'mitigation_source', 'mitigation_status', 'mitigation_period')):
            raise ValueError('非零缓释能力须提供独立来源与核验状态')
        rows.append({
            **{field: row.get(field) for field in business_fields},
            'relation_id': str(row.get('relation_id') or f'rel-{index + 1:04d}'),
            'source': source, 'target': target, 'weight': float(value) if valid else 0.0,
            'dependency_class': category, 'relation_type': subtype or original,
            'original_relation_type': original or '未分类业务依赖',
            'data_source': row.get('data_source') or '项目既有演示关系记录',
            'reporting_period': row.get('reporting_period') or '未提供',
            'evidence_status': row.get('evidence_status') or '演示记录',
            'direction_basis': row.get('direction_basis') or '演示方向，业务角色待核验',
            'active': not reasons and value > 0,
            'pending_reason': '；'.join(reasons) or ('依赖强度为零' if value == 0 else ''),
            'mitigation_capacity': float(capacity),
            **{field: row.get(field) or '' for field in ('mitigation_mechanism', 'mitigation_source', 'mitigation_status', 'mitigation_period')},
        })
    return pd.DataFrame(rows, columns=columns)


def support_risk_nodes(support: pd.DataFrame | None, company_ids: set) -> pd.DataFrame:
    columns = ['company_id', 'company_name', 'node_type', 'initial_risk', 'risk_source', 'reporting_period']
    if support is None or support.empty:
        return pd.DataFrame(columns=columns)
    if not set(SUPPORT_COLUMNS).issubset(support.columns):
        raise ValueError('公共支撑节点缺少身份、类型或运行风险依据')
    if support.node_id.duplicated().any() or set(support.node_id) & company_ids:
        raise ValueError('公共支撑节点编号须唯一且不可与企业编号重叠')
    for row in support.itertuples():
        if not isinstance(row.node_id, str) or not row.node_id.strip() or not isinstance(row.node_name, str) or not row.node_name.strip():
            raise ValueError('公共支撑节点编号与名称不能为空')
        if row.node_type not in ('energy', 'infra'):
            raise ValueError('公共支撑节点类型须为 energy 或 infra')
        if not math.isfinite(float(row.initial_risk)) or not 0 <= float(row.initial_risk) <= 1:
            raise ValueError('公共支撑节点风险须为 0–1 的有限数值')
        if not isinstance(row.risk_source, str) or not row.risk_source.strip() or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(row.reporting_period)):
            raise ValueError('公共支撑节点须提供风险来源与 YYYY-MM 报告期')
    return support[SUPPORT_COLUMNS].rename(columns={'node_id': 'company_id', 'node_name': 'company_name'})


def prepare_network(nodes: pd.DataFrame, edges: pd.DataFrame, edge_scale: float = 1.0, relation_weights: dict | None = None) -> dict:
    if not math.isfinite(edge_scale) or not 0 <= edge_scale <= 1:
        raise ValueError('网络边缩放须为 0–1 的有限数值')
    ids = nodes.company_id.tolist()
    index = {node_id: i for i, node_id in enumerate(ids)}
    coefficients = relation_coefficients(relation_weights)
    relations = normalize_relations(edges, set(ids))
    layers = {key: np.zeros((len(ids), len(ids))) for key in RELATION_CLASSES}
    for row in relations.itertuples():
        if row.active:
            layers[row.dependency_class][index[row.target], index[row.source]] += row.weight
    weighted = sum(coefficients[key] * layers[key] for key in RELATION_CLASSES) * edge_scale
    divisor = np.maximum(weighted.sum(axis=1), 1.0)
    matrix = weighted / divisor[:, None]
    relations['category_coefficient'] = [coefficients.get(key, 0) for key in relations.dependency_class]
    relations['effective_weight'] = [
        row.weight * coefficients[row.dependency_class] * edge_scale / divisor[index[row.target]] if row.active else 0.0
        for row in relations.itertuples()
    ]
    protection = np.zeros_like(matrix)
    for row in relations.itertuples():
        if row.effective_weight > 0:
            protection[index[row.target], index[row.source]] += row.effective_weight * row.mitigation_capacity
    return {'matrix': matrix, 'mitigation_matrix': protection, 'layers': layers, 'relations': relations, 'coefficients': coefficients}


def path_components(keys, prepared, own_risk, decay):
    """Gross path risk minus explicit protection; two-hop protection needs both links."""
    matrix, protection = prepared['matrix'], prepared['mitigation_matrix']
    weight = capacity = decay ** (len(keys)-1)
    for source, target in zip(keys, keys[1:]):
        weight *= matrix[target, source]
        capacity *= protection[target, source]
    gross = float(weight * own_risk[keys[0]])
    return {'gross_contribution': gross, 'mitigation_contribution': float(capacity),
            'contribution': gross-float(capacity)}


def affected_credit_exposure(companies: pd.DataFrame, edges: pd.DataFrame, company_id: str,
                             support_nodes: pd.DataFrame | None = None, relation_weights: dict | None = None) -> dict:
    company_ids = set(companies.company_id)
    if company_id not in company_ids:
        raise KeyError(f'企业不存在：{company_id}')
    support = support_risk_nodes(support_nodes, company_ids)
    known_ids = company_ids | set(support.company_id)
    coefficients = relation_coefficients(relation_weights)
    relations = normalize_relations(edges, known_ids)
    active = relations.loc[relations.active & relations.dependency_class.map(coefficients).fillna(0).gt(0)]
    depths, frontier = {company_id: 0}, {company_id}
    for depth in (1, 2):
        frontier = set(active.loc[active.source.isin(frontier), 'target']) - depths.keys()
        depths.update({node_id: depth for node_id in frontier})
    eligible = companies.get('financing_eligible', pd.Series(True,index=companies.index)).astype(bool)
    covered = companies.loc[companies.company_id.isin(depths) & eligible, ['company_id', 'company_name', 'industry', 'base_limit']].copy()
    covered['propagation_order'] = covered.company_id.map(depths)
    covered = covered.sort_values(['propagation_order', 'company_id'])
    totals = {order: float(covered.loc[covered.propagation_order == order, 'base_limit'].sum()) for order in (0, 1, 2)}
    total, park_total = float(covered.base_limit.sum()), float(companies.base_limit.sum())
    return {'source_company_id': company_id, 'basis': 'base_limit', 'unit': '万元',
            'max_propagation_order': 2, 'includes_source_company': True,
            'total_exposure': total, 'own_exposure': totals[0], 'first_order_exposure': totals[1], 'second_order_exposure': totals[2],
            'company_count': len(covered), 'park_total_exposure': park_total,
            'exposure_share': total / park_total if park_total > 0 else 0.0, 'companies': covered.to_dict(orient='records')}


def propagate_risk(nodes: pd.DataFrame, edges: pd.DataFrame, decay: float = 0.55,
                   edge_scale: float = 1.0, relation_weights: dict | None = None,
                   max_paths: int | None = 3) -> tuple[pd.DataFrame, dict]:
    if not math.isfinite(decay) or not 0 <= decay <= 1:
        raise ValueError('传播衰减系数须为 0–1 的有限数值')
    prepared = prepare_network(nodes, edges, edge_scale, relation_weights)
    matrix = prepared['matrix']
    ids = nodes.company_id.tolist()
    index = {node_id: i for i, node_id in enumerate(ids)}
    initial = nodes.initial_risk.to_numpy(dtype=float)
    protection = prepared['mitigation_matrix']
    first_gross, second_gross = decay * matrix @ initial, decay**2 * matrix @ matrix @ initial
    first_relief, second_relief = decay * protection.sum(axis=1), decay**2 * (protection @ protection).sum(axis=1)
    first, second = first_gross-first_relief, second_gross-second_relief
    result = nodes[['company_id', 'company_name']].copy()
    result['own_risk'], result['first_order_risk'], result['second_order_risk'] = initial, first, second
    result['network_risk'] = np.clip(initial + first + second, 0, 1)
    result['first_order_gross_risk'], result['second_order_gross_risk'] = first_gross, second_gross
    result['first_order_mitigation'], result['second_order_mitigation'] = first_relief, second_relief
    result['network_net_effect'] = first + second
    segments = {}
    for row in prepared['relations'].itertuples():
        if row.effective_weight > 0:
            segments.setdefault((row.source, row.target), []).append({
                'relation_type': row.relation_type, 'dependency_class': row.dependency_class,
                'dependency_weight': row.weight, 'effective_weight': row.effective_weight,
            })
    def segment(source, target):
        return {'source': source, 'target': target, 'channels': segments[(source, target)]}
    paths = {}
    for target in ids:
        t = index[target]
        candidates = []
        for source in ids:
            s = index[source]
            if matrix[t, s] > 0:
                candidates.append({'path': f'{source} -> {target}', 'order': 1,
                                   **path_components([s,t], prepared, initial, decay),
                                   'segments': [segment(source, target)]})
            for middle in ids:
                m = index[middle]
                if matrix[t, m] > 0 and matrix[m, s] > 0:
                    candidates.append({'path': f'{source} -> {middle} -> {target}', 'order': 2,
                                       **path_components([s,m,t], prepared, initial, decay),
                                       'segments': [segment(source, middle), segment(middle, target)]})
        candidates.sort(key=lambda item: (-abs(item['contribution']), item['path']))
        paths[target] = candidates if max_paths is None else candidates[:max_paths]
    return result, paths
