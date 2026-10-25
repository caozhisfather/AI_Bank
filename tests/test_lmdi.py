import math

import pandas as pd

from carbon_finance.lmdi import decompose_lmdi


def test_lmdi_effects_reconcile_to_total_change():
    records = pd.DataFrame(
        [
            [2025, 100, "coal", 40, 2.5],
            [2025, 100, "power", 20, 0.55],
            [2026, 106, "coal", 31, 2.5],
            [2026, 106, "power", 26, 0.55],
        ],
        columns=["period", "output", "energy_type", "energy", "emission_factor"],
    )
    result = decompose_lmdi(records)
    reconstructed = result["activity"] + result["efficiency"] + result["energy_structure"]
    assert math.isclose(reconstructed, result["total_change"], abs_tol=1e-8)
    assert abs(result["residual"]) < 1e-8
    assert result["activity"] > 0
    assert result["efficiency"] < 0


def test_percentages_use_baseline_emissions_and_are_unit_invariant():
    records = pd.DataFrame([
        ['2025-01', 100, 'power', 100, 2],
        ['2025-12', 100, 'power', 80, 2],
    ], columns=['period', 'output', 'energy_type', 'energy', 'emission_factor'])
    result = decompose_lmdi(records)
    assert result['percentage_basis'] == 'base_emissions'
    assert math.isclose(result['total_change_percentage'], -20)
    assert math.isclose(result['effect_percentages']['efficiency'], -20)
    assert result['effect_percentages']['process'] is None
    assert abs(result['effect_percentages']['activity']) < 1e-8
    assert abs(result['effect_percentages']['energy_structure']) < 1e-8
    scaled = records.copy()
    scaled['emission_factor'] *= 1000
    converted = decompose_lmdi(scaled)
    assert math.isclose(converted['total_change'], result['total_change'] * 1000)
    assert math.isclose(converted['total_change_percentage'], -20)
    assert converted['conclusion'] == result['conclusion']


def test_four_factor_route_shift_does_not_double_count_efficiency():
    routes, energy = [], []
    for period, quantities in [('2025-01', [80, 20]), ('2025-12', [40, 70])]:
        for route, quantity, intensity, process_intensity in zip(['blast', 'electric'], quantities, [2, 1], [1, .2]):
            routes.append({'period': period, 'route_id': route, 'output': quantity, 'process_emissions': quantity * process_intensity,
                           'energy_records': [{'energy_type': 'power', 'energy': quantity * intensity, 'emission_factor': 1}]})
        energy.append({'period': period, 'output': sum(quantities), 'energy_type': 'power', 'energy': sum(q * i for q, i in zip(quantities, [2, 1])), 'emission_factor': 1})
    result = decompose_lmdi(pd.DataFrame(energy), routes)
    assert result['process_available']
    assert result['process'] < 0
    assert abs(result['efficiency']) < 1e-8
    assert abs(result['energy_structure']) < 1e-8
    assert result['activity'] > 0
    assert result['base_emissions'] == 264
    assert result['current_emissions'] == 204
    assert abs(result['residual']) < 1e-8
    assert '本期排放较基期下降22.73%' in result['conclusion']
    assert '工艺调整是主要减排来源（贡献−' in result['conclusion']
    assert '企业在扩大生产的同时实现了排放下降' in result['conclusion']


def test_introduced_energy_and_zero_process_reconcile():
    records = pd.DataFrame([
        {'period': '2025-01', 'output': 100, 'energy_type': 'coal', 'energy': 50, 'emission_factor': 2},
        {'period': '2025-12', 'output': 100, 'energy_type': 'power', 'energy': 40, 'emission_factor': 1},
    ])
    result = decompose_lmdi(records)
    assert result['process'] is None  # Missing process data is not a measured zero.
    assert abs(result['residual']) < 1e-7
    routes = [dict(period=row.period, route_id='one', output=row.output, process_emissions=0,
                   energy_records=[dict(energy_type=row.energy_type, energy=row.energy, emission_factor=row.emission_factor)]) for row in records.itertuples()]
    result = decompose_lmdi(records, routes)
    assert result['process_available']
    assert abs(result['process']) < 1e-8
    assert abs(result['residual']) < 1e-7
    assert result['total_change'] == -60


def test_process_coverage_requires_both_periods():
    records = pd.DataFrame([['2025-01', 100, 'power', 50, 1], ['2025-12', 100, 'power', 40, 1]],
                           columns=['period', 'output', 'energy_type', 'energy', 'emission_factor'])
    route = dict(period='2025-12', route_id='one', output=100, process_emissions=20,
                 energy_records=[dict(energy_type='power', energy=40, emission_factor=1)])
    result = decompose_lmdi(records, [route])
    assert result['process'] is None
    assert result['current_emissions'] == 40
    assert result['scope'] == '能源相关排放'


def test_invalid_route_energy_cannot_enter_decomposition():
    import pytest
    records = pd.DataFrame([['2025-01', 100, 'power', 50, 1], ['2025-12', 100, 'power', 40, 1]],
                           columns=['period', 'output', 'energy_type', 'energy', 'emission_factor'])
    route = dict(period='2025-12', route_id='one', output=100, process_emissions=20,
                 energy_records=[dict(energy_type='power', energy=39, emission_factor=1)])
    with pytest.raises(ValueError, match='能耗合计'):
        decompose_lmdi(records, [route])


def test_conclusion_ties_and_production_conditions():
    from carbon_finance.lmdi import attribution_conclusion
    effects = dict(activity=8, efficiency=-14.141, energy_structure=-14.144, process=-4, total_change=-24.285)
    assert attribution_conclusion(effects, 100, 110, True) == '能效改善与能源结构优化共同构成主要减排来源，企业在扩大生产的同时实现了排放下降。'
    effects.update(process=-14.14)
    assert attribution_conclusion(effects, 100, 110, True).startswith('能效改善、能源结构优化、工艺调整共同构成主要减排来源')
    effects.update(activity=-30, efficiency=-5, energy_structure=-4, process=None, total_change=-39)
    assert attribution_conclusion(effects, 100, 80, False) == '在已核算的能源相关排放范围内，产量收缩是主要减排来源，当前排放下降主要由生产规模变化驱动。'
    effects.update(activity=30, total_change=21)
    assert '排放总体上升' in attribution_conclusion(effects, 100, 110, False)
    effects.update(activity=9, total_change=0)
    assert '排放总体持平' in attribution_conclusion(effects, 100, 110, False)
    effects.update(activity=0, total_change=-9)
    assert '产量基本稳定' in attribution_conclusion(effects, 100, 100, True)
    effects.update(efficiency=3, energy_structure=2, total_change=5)
    assert attribution_conclusion(effects, 100, 100, True) == '本期未形成明显减排贡献，企业排放总体上升。'


def test_short_assessment_matches_attribution_including_ties_and_rising_emissions():
    from carbon_finance.lmdi import attribution_summary
    effects=dict(activity=8,efficiency=-14.141,energy_structure=-9,process=None,total_change=-15.141)
    assert attribution_summary(effects)=='能效改善主导'
    effects.update(energy_structure=-14.144)
    assert attribution_summary(effects)=='多因素共同驱动'
    effects.update(activity=-30,efficiency=-5,energy_structure=-4,total_change=-39)
    assert attribution_summary(effects)=='产量收缩主导'
    effects.update(activity=30,total_change=21)
    assert attribution_summary(effects)=='减排尚未抵消增排'
    effects.update(total_change=0)
    assert attribution_summary(effects)=='排放基本持平'
    effects.update(efficiency=2,energy_structure=3,total_change=35)
    assert attribution_summary(effects)=='排放仍在上升'


def test_conclusions_distinguish_companies_with_the_same_reduction_driver():
    results = []
    for current_energy in [80, 90, 120]:
        records = pd.DataFrame([
            ['2025-01', 100, 'power', 100, 1],
            ['2025-12', 100, 'power', current_energy, 1],
        ], columns=['period', 'output', 'energy_type', 'energy', 'emission_factor'])
        results.append(decompose_lmdi(records))
    strong, moderate, rising = results
    assert strong['assessment_summary'] == moderate['assessment_summary'] == '能效改善主导'
    assert '本期排放较基期下降20.00%' in strong['conclusion']
    assert '能效改善是主要减排来源（贡献−20.00个百分点）' in strong['conclusion']
    assert '本期排放较基期下降10.00%' in moderate['conclusion']
    assert '能效改善是主要减排来源（贡献−10.00个百分点）' in moderate['conclusion']
    assert strong['conclusion'] != moderate['conclusion']
    assert '本期排放较基期上升20.00%' in rising['conclusion']
    assert '未形成明显减排贡献' in rising['conclusion']


def test_route_entry_and_retirement_reconcile_as_process_effect():
    records = pd.DataFrame([['2025-01', 100, 'power', 200, 1], ['2025-12', 110, 'power', 110, 1]],
                           columns=['period', 'output', 'energy_type', 'energy', 'emission_factor'])
    routes = [dict(period='2025-01', route_id='old', output=100, process_emissions=60,
                   energy_records=[dict(energy_type='power', energy=200, emission_factor=1)]),
              dict(period='2025-12', route_id='new', output=110, process_emissions=20,
                   energy_records=[dict(energy_type='power', energy=110, emission_factor=1)])]
    result = decompose_lmdi(records, routes)
    assert result['process_available']
    assert result['process'] < 0
    assert abs(result['efficiency']) < 1e-8
    assert abs(result['energy_structure']) < 1e-8
    assert result['total_change'] == -130
    assert abs(result['residual']) < 1e-7
