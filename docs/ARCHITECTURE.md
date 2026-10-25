# 系统架构

## 导入型多智能体链路

```text
本地 JSON / CSV
  -> FastAPI 文件与 Schema 校验
  -> 临时标准化数据集（dataset_id）
  -> 用户选择行业、情景、算法参数和 Agent
  -> LangGraph 状态图
       DataAgent -> TransitionAgent -> ParkRiskAgent
       -> FinanceAgent -> ComplianceAgent
  -> DeepAgents 可选监督汇总
  -> 结论、证据链、执行轨迹
  -> 人工审批
```

LangChain 工具封装确定性数据处理和算法调用，LangGraph 是所有模式下的实际编排引擎。DeepAgents 仅在模型配置可用时承担监督、任务分解和解释，不替代额度、风险传播或 RAROC 计算。无模型密钥时使用离线确定性 Agent，保证现场演示可复现。

上述导入型链路保留用于离线校验和旧数据集历史兼容。现行业务接入改用企业授权接口，旧文件导入 HTTP 入口已关闭；银行账号不能上传企业数据。

```text
Vue 3 / Vite (:5173)
        |
        | REST /api/v1
        v
FastAPI (:8000)
        |
        v
AnalysisService
        |
        +-- AgentWorkflow
        |     DataAgent -> TransitionAgent -> NetworkAgent
        |     -> FinanceAgent -> ComplianceAgent -> 人工审批
        |
        +-- LMDI + LightGBM/SHAP + Isolation Forest
        +-- 两阶园区风险传播
        +-- 动态额度、定价与 RAROC
        |
        v
SQLite 版本化业务数据与核验记录（首次由 CSV 演示数据迁移）
```

前端不保存或计算模型结论，只负责业务展示与交互。后端路由层只处理 HTTP 协议，服务层负责结果整形，`carbon_finance` 保留可独立测试的纯算法模块。

Agent 工作流默认采用离线可运行的确定性编排。五个专业 Agent 分别核验数据、识别转型、分析网络、形成融资建议和检查合规边界；每一步保存证据与建议动作，最终必须进入人工审批。配置 DeepAgents 模型后可启用监督与汇总，但数值仍由确定性工具计算。导入数据集和最近 100 次工作流写入项目内 SQLite，服务重启后可恢复。

## 企业补证与银行审核

企业会话 -> 新报告期接口校验 -> 数据版本 -> 异常任务 -> 企业说明/附件/更正建议 -> 银行审核抽屉 -> 合理结案或更正后新版本 -> 指标重算与审核记录。会话角色、企业归属、材料访问、任务修订号在后端校验。具体边界见 [闭环设计](ENTERPRISE_REVIEW_WORKFLOW.md)。

## 园区有向依赖网络

采购/销售、能源、公共设施三层关系经标准化后合成为同一风险矩阵，传播、路径解释和受影响授信使用同一有效关系范围。Vue 图谱仅筛选展示；来源不明确的旧关系保留为待核验，实际能源与设施节点须带风险来源和报告期。字段、方向和迁移规则见 [有向依赖网络设计](DIRECTED_DEPENDENCY_NETWORK.md)。

## 合并园区风险与压力测试

银行端“园区风险分析”用同一组关系和正常/压力两套计算结果，提供业务依赖与双向风险传导视图。`services/network_analysis.py` 使用归一化矩阵生成完整传入路径和当前企业传出贡献，不将综合风险再次输入传播。详情比较节点风险、融资结果以及主体总变化和本企业贡献变化。企业响应剔除新增的 network_analysis 字段。
