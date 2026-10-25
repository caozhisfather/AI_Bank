from __future__ import annotations

import math

import pandas as pd


def _log_mean(x: float, y: float) -> float:
    if math.isclose(x, y, rel_tol=1e-12):
        return x
    return (x - y) / (math.log(x) - math.log(y))


def validate_route_records(records: list[dict], energy: pd.DataFrame) -> list[dict]:
    """Route quantities reconcile to energy facts; process emissions exclude fuel."""
    if not isinstance(records, list) or not 1 <= len(records) <= 400:
        raise ValueError("工艺明细需为 1–400 条记录")
    checked, seen = [], set()
    for row in records:
        if not isinstance(row, dict) or set(row) != {"period", "route_id", "output", "process_emissions", "energy_records"}:
            raise ValueError("工艺明细需包含 period、route_id、output、process_emissions、energy_records")
        period, route = row["period"], row["route_id"]
        if not isinstance(period, str) or period not in set(energy.period.astype(str)):
            raise ValueError("工艺期间须对应已有或本次提交的能耗期间")
        if not isinstance(route, str) or not route.strip() or len(route) > 80 or (period, route) in seen:
            raise ValueError("同一期工艺路线编号须非空且唯一，长度不超过 80")
        seen.add((period, route))
        for key in ("output", "process_emissions"):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1e12:
                raise ValueError("工艺产量与过程排放须为非负有限数值")
        energies = row["energy_records"]
        if not isinstance(energies, list) or not 1 <= len(energies) <= 20:
            raise ValueError("每条工艺路线需提交 1–20 条能耗记录")
        types = set()
        for item in energies:
            if not isinstance(item, dict) or set(item) != {"energy_type", "energy", "emission_factor"}:
                raise ValueError("工艺能耗需包含 energy_type、energy、emission_factor")
            if not isinstance(item["energy_type"], str) or item["energy_type"] in types:
                raise ValueError("同一工艺路线能源类型不得重复")
            types.add(item["energy_type"])
            for key in ("energy", "emission_factor"):
                value = item[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1e12 or (key == "emission_factor" and value == 0):
                    raise ValueError("工艺能耗须非负，排放因子须为正数且有限")
        total_energy = sum(item["energy"] for item in energies)
        if row["output"] == 0 and (total_energy != 0 or row["process_emissions"] != 0):
            raise ValueError("零产量路线的能耗与过程排放必须为零")
        if row["output"] > 0 and total_energy <= 0:
            raise ValueError("每条工艺路线总能耗须大于零")
        checked.append(row)
    for period in {row["period"] for row in checked}:
        aggregate = energy.loc[energy.period.astype(str) == period]
        routes = [row for row in checked if row["period"] == period]
        if not math.isclose(sum(row["output"] for row in routes), float(aggregate.output.iloc[0]), rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError("工艺路线产量合计须与本期企业产量一致")
        items = [item for row in routes for item in row["energy_records"]]
        if {item["energy_type"] for item in items} != set(aggregate.energy_type):
            raise ValueError("工艺路线能源类型合计须覆盖本期企业能耗")
        for fact in aggregate.itertuples():
            part = [item for item in items if item["energy_type"] == fact.energy_type]
            if not math.isclose(sum(item["energy"] for item in part), fact.energy, rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError("工艺路线能耗合计须与本期企业能耗一致")
            if any(not math.isclose(item["emission_factor"], fact.emission_factor, rel_tol=1e-9) for item in part):
                raise ValueError("同一期工艺与企业能耗须使用一致的排放因子")
    return checked


def _effect(c0: float, c1: float, factor0: float, factor1: float) -> float:
    return _log_mean(c1, c0) * math.log(factor1 / factor0)


def _energy_effects(base: pd.DataFrame, current: pd.DataFrame) -> dict:
    effects = {"activity": 0.0, "efficiency": 0.0, "energy_structure": 0.0}
    q0, q1 = float(base.output.iloc[0]), float(current.output.iloc[0])
    e0, e1 = float(base.energy.sum()), float(current.energy.sum())
    for kind in base.index.union(current.index):
        b = base.loc[kind] if kind in base.index else None
        c = current.loc[kind] if kind in current.index else None
        f0 = float(b.emission_factor if b is not None else c.emission_factor)
        f1 = float(c.emission_factor if c is not None else b.emission_factor)
        # Positive-share limit for introduced/retired energy sources.
        s0 = max(float(b.energy / e0) if b is not None else 0, 1e-12)
        s1 = max(float(c.energy / e1) if c is not None else 0, 1e-12)
        c0, c1 = e0 * s0 * f0, e1 * s1 * f1
        effects["activity"] += _effect(c0, c1, q0, q1)
        effects["efficiency"] += _effect(c0, c1, e0 / q0, e1 / q1)
        effects["energy_structure"] += _effect(c0, c1, s0 * f0, s1 * f1)
    return effects


def _route_effects(routes: list[dict], periods: list, base: pd.DataFrame, current: pd.DataFrame) -> dict | None:
    groups = [{row["route_id"]: row for row in routes if row["period"] == str(period)} for period in periods]
    if not all(groups):
        return None
    effects = {"activity": 0.0, "efficiency": 0.0, "energy_structure": 0.0, "process": 0.0}
    q0, q1 = float(base.output.iloc[0]), float(current.output.iloc[0])
    for route in sorted(groups[0].keys() | groups[1].keys()):
        actual0, actual1 = groups[0].get(route), groups[1].get(route)
        if not (actual0 and actual0["output"]) and not (actual1 and actual1["output"]):
            continue
        # Entry/exit is assigned to the route-share effect in the positive-share limit.
        # Inherit within-route coefficients from the active period, avoiding spurious efficiency changes.
        b = actual0 if actual0 and actual0["output"] else actual1
        c = actual1 if actual1 and actual1["output"] else actual0
        s0 = max(actual0["output"] / q0 if actual0 else 0, 1e-12)
        s1 = max(actual1["output"] / q1 if actual1 else 0, 1e-12)
        e0, e1 = sum(x["energy"] for x in b["energy_records"]), sum(x["energy"] for x in c["energy_records"])
        i0, i1 = e0 / b["output"], e1 / c["output"]
        energy0 = {x["energy_type"]: x for x in b["energy_records"]}
        energy1 = {x["energy_type"]: x for x in c["energy_records"]}
        for kind in energy0.keys() | energy1.keys():
            r0, r1 = energy0.get(kind), energy1.get(kind)
            f0, f1 = (r0 or r1)["emission_factor"], (r1 or r0)["emission_factor"]
            m0 = max(r0["energy"] / e0 if r0 else 0, 1e-12)
            m1 = max(r1["energy"] / e1 if r1 else 0, 1e-12)
            c0, c1 = q0 * s0 * i0 * m0 * f0, q1 * s1 * i1 * m1 * f1
            effects["activity"] += _effect(c0, c1, q0, q1)
            effects["efficiency"] += _effect(c0, c1, i0, i1)
            effects["energy_structure"] += _effect(c0, c1, m0 * f0, m1 * f1)
            effects["process"] += _effect(c0, c1, s0, s1)
        p0 = max(b["process_emissions"] / b["output"], 1e-12)
        p1 = max(c["process_emissions"] / c["output"], 1e-12)
        c0, c1 = q0 * s0 * p0, q1 * s1 * p1
        effects["activity"] += _effect(c0, c1, q0, q1)
        effects["process"] += _effect(c0, c1, s0 * p0, s1 * p1)
    effects["base_process_emissions"] = sum(row["process_emissions"] for row in groups[0].values())
    effects["current_process_emissions"] = sum(row["process_emissions"] for row in groups[1].values())
    return effects


def reduction_leaders(effects: dict) -> list[str]:
    displayed = effects.get("effect_percentages", effects)
    reductions = {key: round(-displayed[key] + 1e-10, 2) for key in ('activity','efficiency','energy_structure','process') if displayed.get(key) is not None and round(displayed[key], 2) < 0}
    if not reductions:
        return []
    largest = max(reductions.values())
    return [key for key,value in reductions.items() if value==largest]


def attribution_summary(effects: dict) -> str:
    change = round(effects.get('total_change_percentage',effects['total_change']),2)
    leaders = reduction_leaders(effects)
    if change>0:
        return '减排尚未抵消增排' if leaders else '排放仍在上升'
    if change==0:
        return '排放基本持平'
    if len(leaders)>1:
        return '多因素共同驱动'
    return {'activity':'产量收缩主导','efficiency':'能效改善主导',
            'energy_structure':'能源结构主导','process':'工艺改善主导'}.get(leaders[0] if leaders else '', '暂无明确减排来源')


def attribution_conclusion(effects: dict, base_output: float, current_output: float, process_available: bool) -> str:
    names = {"activity": "产量收缩", "efficiency": "能效改善", "energy_structure": "能源结构优化", "process": "工艺调整"}
    leader_keys = reduction_leaders(effects)
    prefix = "" if process_available else "在已核算的能源相关排放范围内，"
    change = round(effects.get("total_change_percentage", effects["total_change"]), 2)
    percentages = effects.get("effect_percentages")
    quantified = percentages is not None and "total_change_percentage" in effects
    if quantified:
        net = f"本期排放较基期{'下降' if change < 0 else '上升'}{abs(change):.2f}%" if change else "本期排放较基期基本持平"
        prefix += f"{net}；"
    if not leader_keys:
        ending = "总体上升" if change > 0 else "总体持平"
        return f"{prefix}本期未形成明显减排贡献，企业排放{ending}。"
    leaders = [names[key] for key in leader_keys]
    subject = "与".join(leaders) if len(leaders) <= 2 else "、".join(leaders)
    main = f"{subject}{'是' if len(leaders) == 1 else '共同构成'}主要减排来源"
    if quantified:
        contributions = "、".join(f"{percentages[key]:+.2f}".replace("-", "−") for key in leader_keys)
        main += f"（{'分别' if len(leader_keys) > 1 else ''}贡献{contributions}个百分点）"
    if change > 0:
        ending = "但其减排效果尚未抵消增排因素，企业排放总体上升"
    elif change == 0:
        ending = "各因素影响相互抵消，企业排放总体持平"
    elif math.isclose(base_output, current_output, rel_tol=1e-6):
        ending = "企业在产量基本稳定的情况下实现了排放下降"
    elif current_output > base_output:
        ending = "企业在扩大生产的同时实现了排放下降"
    elif leaders == ["产量收缩"]:
        ending = "当前排放下降主要由生产规模变化驱动"
    else:
        ending = "排放下降同时伴随产量收缩"
    return f"{prefix}{main}，{ending}。"


def decompose_lmdi(records: pd.DataFrame, route_records: list[dict] | None = None) -> dict:
    """LMDI of energy plus optional route share and non-fuel process emissions."""
    required = {"period", "output", "energy_type", "energy", "emission_factor"}
    if not required.issubset(records.columns):
        raise ValueError(f"LMDI 数据缺少字段：{sorted(required - set(records.columns))}")
    periods = sorted(records["period"].unique())
    if len(periods) != 2:
        raise ValueError("LMDI 分解需要且仅需要两个观察期")
    frames = []
    for period in periods:
        part = records.loc[records.period == period].copy()
        if part.energy_type.duplicated().any() or part.output.nunique() != 1:
            raise ValueError("同一期能源类型须唯一，且产量必须一致")
        values = part[["energy", "output", "emission_factor"]].to_numpy(dtype=float)
        if not math.isfinite(float(values.sum())) or (values[:, 0] < 0).any() or (values[:, 1:] <= 0).any() or part.energy.sum() <= 0:
            raise ValueError("能耗须非负且总量大于零，产量与因子须为正数且有限")
        frames.append(part.set_index("energy_type"))
    base, current = frames
    energy_base = float((base.energy * base.emission_factor).sum())
    energy_current = float((current.energy * current.emission_factor).sum())
    effects = _energy_effects(base, current)
    selected = [row for row in (route_records or []) if row["period"] in {str(p) for p in periods}]
    route_effects = _route_effects(validate_route_records(selected, records), periods, base, current) if selected else None
    available = route_effects is not None
    if available:
        effects = route_effects
    else:
        effects["process"] = None
    total_base = energy_base + effects.get("base_process_emissions", 0)
    total_current = energy_current + effects.get("current_process_emissions", 0)
    total_change = total_current - total_base
    residual = total_change - sum(effects[key] or 0 for key in ("activity", "efficiency", "energy_structure", "process"))
    if abs(residual) > max(1e-7, 1e-9 * max(total_base, total_current)):
        raise ValueError("归因结果未能与核算范围内的排放变化对齐，请核验输入数据")
    effects.update({"base_emissions": total_base, "current_emissions": total_current, "total_change": total_change, "residual": residual,
                    "process_available": available, "base_period": str(periods[0]), "current_period": str(periods[-1]),
                    "scope": "能源与已纳入核算的工艺过程排放" if available else "能源相关排放", "unit": "原始数据核算单位"})
    effects["percentage_basis"] = "base_emissions"
    effects["effect_percentages"] = {
        key: effects[key] / total_base * 100 if effects[key] is not None else None
        for key in ("activity", "efficiency", "energy_structure", "process")
    }
    effects["total_change_percentage"] = total_change / total_base * 100
    effects["conclusion"] = attribution_conclusion(effects, float(base.output.iloc[0]), float(current.output.iloc[0]), available)
    effects['assessment_summary'] = attribution_summary(effects)
    return effects
