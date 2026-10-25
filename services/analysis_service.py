from __future__ import annotations

from functools import lru_cache
from functools import wraps
import math
from threading import RLock

import numpy as np
import pandas as pd

from carbon_finance.config import SCENARIOS, DEMO_PARAMS, NETWORK_RELATION_WEIGHTS
from carbon_finance.network import affected_credit_exposure, prepare_network, support_risk_nodes, RELATION_CLASSES
from carbon_finance.pipeline import CarbonFinancePipeline
from services.agent_workflow import AgentWorkflow
from services.business_store import business_store
from services.network_analysis import explain_network


def database_snapshot(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock, self.store.lock:
            self.refresh()
            return method(self, *args, **kwargs)
    return call


def _native(value):
    if isinstance(value, dict):
        return {key: _native(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_native(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    cleaned = frame.replace({np.nan: None})
    return _native(cleaned.to_dict(orient="records"))


class AnalysisService:
    def __init__(self) -> None:
        self.lock = RLock()
        self.store = business_store
        self.store.seed()
        data, _ = self.store.load_data()
        self.pipeline = CarbonFinancePipeline(data=data)
        self.agent_workflow = AgentWorkflow()

    def refresh(self):
        data, versions = self.store.load_data()
        self.pipeline.data = data
        raw = self.pipeline.evaluate_entities()
        self.store.reconcile_tasks(versions, raw)
        self.pipeline.reviewed_company_ids = self.store.approved_model_versions()

    @database_snapshot
    def metadata(self) -> dict:
        companies = self.pipeline.data["companies"]
        return {
            "companies": _records(companies[[key for key in ('company_id','company_name','industry','business_role','node_type','evaluation_model','in_park') if key in companies]]),
            "scenarios": list(SCENARIOS),
            "scenario_catalog": [
                {"name": name, **settings} for name, settings in SCENARIOS.items()
            ],
            "terminals": {
                "银行端": ["转型可信度评价", "园区风险分析", "融资决策", "审核任务清单"],
                "企业端": ["转型账户", "转型路径", "真实减排", "转型可信度", "融资方案", "数据接入与补充材料"],
            },
            "model_auc": self.pipeline.transition_engine.auc,
            "network_relation_classes": [{"key": key, **value} for key, value in RELATION_CLASSES.items()],
            "disclaimer": "模拟数据与演示参数，仅用于竞赛算法原型验证，不构成正式授信结论。",
        }

    @database_snapshot
    def dashboard(self, scenario: str) -> dict:
        result = self.pipeline.run(scenario)
        companies = result["companies"]
        columns = [
            "company_id", "company_name", "industry", "base_limit", "project_need",
            "p_target", "transition_score", "data_quality", "anomaly_score",
            "own_risk", "first_order_risk", "second_order_risk", "network_risk",
            "transition_support", "network_deduction", "final_limit", "suggested_rate",
            "raroc", "warning_level", "action",
        ]
        return {
            "scenario": scenario,
            "summary": {
                "company_count": len(companies),
                "base_exposure": float(companies["base_limit"].sum()),
                "project_need": float(companies["project_need"].sum()),
                "alerts": int(companies["warning_level"].str.contains("关注|干预").sum()),
            },
            "companies": _records(companies[columns]),
        }

    @database_snapshot
    def company_analysis(self, company_id: str, scenario: str) -> dict:
        detail = self.pipeline.company_detail(company_id, scenario)
        normal = self.pipeline.company_detail(company_id, "正常情景")
        stress = self.pipeline.company_detail(company_id, "天然气价格上涨30%")
        feature = self.pipeline.data["features"].loc[
            self.pipeline.data["features"]["company_id"] == company_id
        ].iloc[0]
        energy_history = self.pipeline.data["energy"].loc[
            self.pipeline.data["energy"]["company_id"] == company_id
        ].copy()
        energy_history["emissions"] = energy_history["energy"] * energy_history["emission_factor"]
        carbon_trend = energy_history.groupby("period", as_index=False).agg(
            emissions=("emissions", "sum"), output=("output", "max")
        )
        carbon_trend["carbon_intensity"] = carbon_trend["emissions"] / carbon_trend["output"]
        company = detail["company"]
        prepared, baseline_prepared = detail['prepared_network'], normal['prepared_network']
        graph = self._network_graph(company_id, detail['network'], normal['network'], detail['companies'], normal['companies'], prepared, baseline_prepared)
        common = {
            'scenario': scenario, 'company': company,
            'data_version': {key:self.store.latest(company_id)[key] for key in ('id','version','period','source','created_at')},
            'network': _records(detail['network']), 'network_graph': graph,
            'network_analysis': explain_network(company_id,detail['network'],normal['network'],prepared,baseline_prepared),
            'risk_paths':detail['top_paths'],
            'affected_credit_exposure':affected_credit_exposure(self.pipeline.data['companies'],self.pipeline.data['network'],company_id,support_nodes=self.pipeline.data.get('support_nodes'),relation_weights=NETWORK_RELATION_WEIGHTS),
            'comparison':{'normal':normal['company'],'stress':stress['company'],'selected':company},
            'model_auc':detail['model_auc'],
        }
        if company.get('evaluation_model') == 'operating':
            history=self.pipeline.data.get('service_history',pd.DataFrame())
            rows=history.loc[history.company_id==company_id] if not history.empty else history
            profile=self.pipeline.data['operation_profiles'].set_index('company_id').loc[company_id].to_dict()
            return _native({**common,'lmdi':None,'shap':[],'shap_probability':None,
                            'operating_profile':profile,'service_history':_records(rows),
                            'evaluation_note':'运行与履约风险分析；未适配钢铁转型预测及融资模型'})
        return _native({
            "scenario": scenario,
            "data_version": {key: self.store.latest(company_id)[key] for key in ("id", "version", "period", "source", "created_at")},
            "company": company,
            "transition_credibility": {
                "score": 100 * company["p_target"] * company["data_quality"],
                "max_score": 100,
                "method": "quality_adjusted_probability",
                "p_target": company["p_target"],
                "data_quality": company["data_quality"],
            },
            "project": {
                "name": company["project_name"],
                "progress": feature["project_progress"],
                "own_fund_arrival": feature["own_fund_arrival"],
                "fund_usage_match": feature["fund_usage_match"],
                "milestone_delay_days": feature["milestone_delay_days"],
            },
            "transition_evidence": {
                "emissions": {
                    "base_period": str(carbon_trend["period"].iloc[0]),
                    "current_period": str(carbon_trend["period"].iloc[-1]),
                    "efficiency_effect": detail["lmdi"]["efficiency"],
                    "energy_structure_effect": detail["lmdi"]["energy_structure"],
                    "net_change": detail["lmdi"]["total_change"],
                },
                "project": {
                    "progress": feature["project_progress"],
                    "milestone_delay_days": feature["milestone_delay_days"],
                },
                "funds": {
                    "usage_match": feature["fund_usage_match"],
                    "own_fund_arrival": feature["own_fund_arrival"],
                },
                "data": {
                    "completeness": feature["data_completeness"],
                    "rule_quality": company["data_quality"],
                    "anomaly_score": company["anomaly_score"],
                    "raw_quality": company["raw_data_quality"],
                    "reviewed": company["anomaly_reviewed"],
                },
            },
            "monitoring": {
                "observation_period_days": 30 if company["warning_level"].startswith("红色") else 60 if company["warning_level"].startswith("橙色") else 90,
                "next_review_items": ["能耗与产量月报", "项目里程碑证明", "贷款支付与发票", "核心上下游变化"],
                "alerts": [
                    {
                        "type": "资金偏离",
                        "level": "关注" if feature["fund_usage_match"] < 0.9 else "正常",
                        "evidence": f"资金用途一致率 {feature['fund_usage_match']:.1%}",
                        "action": "核验设备合同、发票与付款路径",
                    },
                    {
                        "type": "项目偏离",
                        "level": "关注" if feature["milestone_delay_days"] > 15 else "正常",
                        "evidence": f"里程碑延迟 {feature['milestone_delay_days']:.0f} 天",
                        "action": "复核施工计划和设备投产证明",
                    },
                    {
                        "type": "绩效偏离",
                        "level": "关注" if company["p_target"] < 0.7 else "正常",
                        "evidence": f"未来12个月达标概率 {company['p_target']:.1%}",
                        "action": "缩短观察期并更新能耗绩效数据",
                    },
                    {
                        "type": "数据异常",
                        "level": "已核验合理" if company["anomaly_reviewed"] else "关注" if company["anomaly_score"] >= 0.4 else "正常",
                        "evidence": f"组合异常分数 {company['anomaly_score']:.1%}",
                        "action": "发起第三方数据与现场人工核验",
                    },
                ],
            },
            "lmdi": detail["lmdi"],
            "carbon_trend": _records(carbon_trend),
            "shap": _records(detail["shap"]),
            "shap_probability": detail["shap_probability"],
            "risk_paths": detail["top_paths"],
            "network": _records(detail["network"]),
            "network_graph": graph,
            "network_analysis": explain_network(company_id, detail['network'], normal['network'], prepared, baseline_prepared),
            "affected_credit_exposure": affected_credit_exposure(
                self.pipeline.data["companies"], self.pipeline.data["network"], company_id,
                support_nodes=self.pipeline.data.get("support_nodes"), relation_weights=NETWORK_RELATION_WEIGHTS,
            ),
            "comparison": {
                "normal": normal["company"],
                "stress": stress["company"],
                "selected": company,
            },
            "model_auc": detail["model_auc"],
        })

    def _network_graph(self, company_id: str, network: pd.DataFrame, baseline: pd.DataFrame, decisions: pd.DataFrame, baseline_decisions: pd.DataFrame, prepared: dict, baseline_prepared: dict) -> dict:
        relations = prepared["relations"].copy()
        risk_map = network.set_index("company_id")["network_risk"].to_dict()
        companies = self.pipeline.data["companies"][[key for key in ('company_id','company_name','industry','node_type','short_name','business_role','product','process_route','in_park','evaluation_model') if key in self.pipeline.data['companies']]].copy()
        if 'node_type' not in companies:
            companies["node_type"] = "enterprise"
        companies['can_analyze'] = True
        support = support_risk_nodes(self.pipeline.data.get("support_nodes"), set(companies.company_id))
        if not support.empty:
            support = support.copy()
            support["industry"] = support.node_type.map({"energy": "能源供应", "infra": "公共设施"})
            companies = pd.concat([companies, support], ignore_index=True)
        companies["risk"] = companies.company_id.map(risk_map)
        companies["selected"] = companies.company_id == company_id
        normal = baseline.set_index('company_id')
        current = network.set_index('company_id')
        for key in ('own_risk', 'first_order_risk', 'second_order_risk', 'network_risk', 'first_order_gross_risk', 'second_order_gross_risk', 'first_order_mitigation', 'second_order_mitigation'):
            companies[key] = companies.company_id.map(current[key])
            companies[f'baseline_{key}'] = companies.company_id.map(normal[key])
        companies['baseline_risk'] = companies.baseline_network_risk
        companies['risk_delta'] = companies.risk - companies.baseline_risk
        for key in ('final_limit', 'warning_level'):
            companies[key] = companies.company_id.map(decisions.set_index('company_id')[key])
            companies[f'baseline_{key}'] = companies.company_id.map(baseline_decisions.set_index('company_id')[key])
        names = companies.set_index("company_id")["company_name"].to_dict()
        relations["source_name"] = relations.source.map(names).fillna(relations.source)
        relations["target_name"] = relations.target.map(names).fillna(relations.target)
        def dependency_description(row):
            source, target = row.source_name, row.target_name
            if row.relation_type == '采购依赖':
                return f'{target}从{source}采购，对其供应存在依赖'
            if row.relation_type == '销售依赖':
                return f'{target}向{source}销售，对其客户需求存在依赖'
            if row.dependency_class == 'energy':
                return f'{target}对{source}的能源供给存在依赖'
            if row.dependency_class == 'infra':
                return f'{target}对{source}提供的公共设施服务存在依赖'
            return f'{target}依赖{source}'
        relations['dependency_description'] = [dependency_description(row) for row in relations.itertuples()]
        relations['dependent_id'] = relations.target
        relations['provider_id'] = relations.source
        decay = DEMO_PARAMS['propagation_decay']
        baseline_relations = baseline_prepared['relations'].set_index('relation_id')
        relations['baseline_mitigation_capacity'] = relations.relation_id.map(baseline_relations.mitigation_capacity)
        relations['gross_contribution'] = [float(decay*r.effective_weight*current.loc[r.source,'own_risk']) if r.effective_weight>0 else 0 for r in relations.itertuples()]
        relations['mitigation_contribution'] = decay * relations.effective_weight * relations.mitigation_capacity
        relations['direct_contribution'] = relations.gross_contribution-relations.mitigation_contribution
        relations['baseline_gross_contribution'] = [float(decay*r.effective_weight*normal.loc[r.source,'own_risk']) if r.effective_weight>0 else 0 for r in relations.itertuples()]
        relations['baseline_mitigation_contribution'] = decay * relations.effective_weight * relations.baseline_mitigation_capacity
        relations['baseline_direct_contribution'] = relations.baseline_gross_contribution-relations.baseline_mitigation_contribution
        relations['contribution_delta'] = relations.direct_contribution-relations.baseline_direct_contribution
        active = relations.loc[relations.effective_weight > 0]
        pending = relations.loc[~relations.active]
        return {"nodes": _records(companies), "edges": _records(active), "pending_edges": _records(pending),
                "direction": "source_to_dependent", "scope": "all_park",
                "relation_classes": [{"key": key, **value, "coefficient": prepared["coefficients"][key],
                                      "count": int((active.dependency_class == key).sum())} for key, value in RELATION_CLASSES.items()]}

    def workflow(self, company_id: str, scenario: str) -> dict:
        analysis=self.company_analysis(company_id, scenario)
        if analysis['company'].get('evaluation_model') == 'operating':
            raise ValueError('该主体使用运行风险模板，未适配转型融资工作流')
        return _native(self.agent_workflow.run(analysis))


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    return AnalysisService()
