# 实时计算展示与后台数据接入

银行端新增“计算工作流”，位于侧栏其他四个功能之后；登录后默认进入转型可信度评价。选取企业和分析情景，进入计算工作流并点击“运行完整分析”。页面无文件选择、数据编辑或导入按钮；企业端的数据页也只保留数据版本查看和证明材料补充。

## 计算方式

每次运行由 `POST /api/v1/companies/{company_id}/analysis-workflow` 发起。请求仅接受分析情景，不接受企业数据、模型结果或上传文件。后端在工作线程中读取一次数据库快照，然后以 NDJSON 逐条发送实际阶段事件；Nginx 通过 `X-Accel-Buffering: no` 禁止缓冲该响应。

1. 从版本化数据库读取企业事实，记录版本、来源、期间和输入记录数。
2. 对本次快照执行 LMDI 减排归因。
3. 使用现有 LightGBM、Isolation Forest 和概率空间 SHAP 计算预测、异常与解释。
4. 通过现有园区风险算法计算自身、一阶和二阶风险。
5. 调用现有融资算法计算额度、定价及 RAROC。
6. 分别计算正常情景和天然气价格上涨 30% 情景。
7. 基于实际入库事实生成核验任务，并将事件、结果、耗时和版本保存至 `analysis_workflow_runs`。

阶段状态在真正执行前后产生，不使用定时器伪造进度。后端出错则停止后续步骤并记录失败；连接中断不会展示为完成。前端图表出现时的淡入动画只用于展示已返回结果。用户离开页面或停止接收时会取消连接。工作流至多同时运行两项任务，不自动审批或改变授信合同。

压力测试的假设变化不会被写成企业实际经营事实。计算期间如后台更换数据版本，完成结果保留原版本，并提示重新运行。计算历史接口为 `GET /api/v1/companies/{company_id}/analysis-workflows`，仅银行角色可访问。

## 后台接入

使用管理员终端从完整 CSV 目录接入业务快照。先激活环境：

```powershell
conda activate pytorch_env
```

以下命令只做结构、数值、关联关系、LMDI 和算法可运行性校验，不修改业务数据库：

```powershell
python scripts/import_backend_data.py --source-dir "D:/business-data" --source-label "按实际情况填写数据来源和用途"
```

校验无误后显式执行入库：

```powershell
python scripts/import_backend_data.py --source-dir "D:/business-data" --source-label "按实际情况填写数据来源和用途" --apply
```

输入目录须包含 `companies.csv`、`energy_performance.csv`、`transition_features.csv`、`network_edges.csv`、`transition_projects.csv`、`fund_usage.csv`、`external_risks.csv` 和 `training_samples.csv`，字段采用项目 `data/` 中现有表结构。能源、公共设施、风险缓释和历史台账等可选表也会读取。

导入前自动备份 SQLite 数据库；所有表在一个事务内入库。每家企业产生新的数据版本，原版本、证明材料和审核记录保留；同一快照再次导入不会重复产生版本。完整快照不允许遗漏数据库已有企业。导入批次、文件摘要和原参考表保存在 `backend_import_batches`。不会覆盖源 CSV 或清理历史文件。

旧 `/datasets/import` 不对银行开放；企业端也不能用它上传业务数据。外部企业系统的既有授权同步接口保留兼容，但不再在网页提供请求编辑、示例数据生成或发送按钮。证明材料补充属于人工核验流程，不属于业务数据批量导入。

导入后刷新工作台即可读取新事实。若训练样本也发生变化，需重启后端，以便其他现有分析页面重新初始化模型；完整计算工作流本身每次从当前快照初始化计算。

## 来源与使用边界

前端保留真实的数据来源说明和版本，不将自建场景数据表述为企业实测或银行已核验数据。运行中的阶段与结果由现有代码实际计算；数据集上的模型指标、案例参数与实际银行授信结论仍应区分。
