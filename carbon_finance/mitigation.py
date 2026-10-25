"""Explicit, independently sourced protection parameters; never signed dependency weights."""
import math

import pandas as pd

from .network import RELATION_ALIASES

PROFILE_COLUMNS = ['source', 'target', 'relation_type', 'coverage_ratio', 'effectiveness',
                   'availability', 'stress_sensitivity', 'mechanism', 'data_source',
                   'reporting_period', 'evidence_status']


def apply_mitigation_profiles(edges, profiles=None, shock=0, scenario=None):
    result = edges.copy()
    result['mitigation_capacity'] = 0.0
    result['mitigation_mechanism'] = ''
    result['mitigation_source'] = ''
    result['mitigation_status'] = ''
    result['mitigation_period'] = ''
    if profiles is None or profiles.empty:
        return result
    if not set(PROFILE_COLUMNS).issubset(profiles.columns):
        raise ValueError('缓释参数缺少覆盖率、有效性、可用性或依据')
    canonical = lambda value: RELATION_ALIASES.get(value, (None, value))[1]
    profile_keys = set()
    for row in profiles.itertuples():
        key = (row.source, row.target, canonical(row.relation_type))
        if key in profile_keys:
            raise ValueError('同一依赖关系的缓释参数不可重复')
        profile_keys.add(key)
        for field in ('coverage_ratio', 'effectiveness', 'availability', 'stress_sensitivity'):
            value = getattr(row, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('缓释比例和情景敏感度须为 0–1 的有限数值')
        if any(not isinstance(getattr(row, field), str) or not getattr(row, field).strip()
               for field in ('mechanism', 'data_source', 'reporting_period', 'evidence_status')):
            raise ValueError('缓释参数须有机制、来源、报告期和核验状态')
        matched = (result.source == row.source) & (result.target == row.target) & (result.relation_type.map(canonical) == key[2])
        if not matched.any():
            raise ValueError(f'缓释参数未匹配到依赖关系：{row.source} → {row.target}')
        reference = getattr(row, 'stress_reference_change', 1.)
        if pd.isna(reference): reference = 1.
        if not math.isfinite(reference) or not 0 < reference <= 1:
            raise ValueError('缓释压力参考变化须在0至1之间')
        driver = getattr(row, 'stress_driver', '')
        applied_shock = shock if not isinstance(driver,str) or not driver or not scenario or driver==scenario.get('driver') else 0
        capacity = row.coverage_ratio * row.effectiveness * row.availability * max(0, 1-applied_shock/reference*row.stress_sensitivity)
        result.loc[matched, 'mitigation_capacity'] = capacity
        for column, value in [('mitigation_mechanism', row.mechanism), ('mitigation_source', row.data_source),
                              ('mitigation_period', row.reporting_period), ('mitigation_status', row.evidence_status)]:
            result.loc[matched, column] = value
    return result
