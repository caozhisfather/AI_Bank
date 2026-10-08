# AI_Bank｜工银“碳跃智衡”

面向高碳产业园区的可信转型融资与动态风险管理平台。项目将企业转型数据转化为银行可解释、可追溯的辅助决策信号，形成“真实转型识别 -> 园区关联风险 -> 动态融资决策”的完整计算链。

> 本仓库是竞赛算法原型，全部企业、交易、授信和模型数据均为模拟数据；支持比例、网络参数、RAROC 阈值等均为演示参数。输出仅为辅助决策建议，不代表工商银行真实客户、内部模型、正式授信结论或合同调整。

## 1. MVP 目标

原型围绕三分钟路演主线实现：

1. 企业申请转型项目融资，展示基础授信和项目资金需求。
2. LMDI 分解排放变化，识别减排来自产量、能效还是能源结构。
3. LightGBM 预测未来 12 个月转型目标达标概率，SHAP 输出关键驱动因素。
4. Isolation Forest 识别能耗、项目进度和资金使用的异常组合，只触发人工核验提示。
5. 加权有向网络计算自身、一阶和二阶关联风险，并给出主要传播路径。
6. 在正常与能源价格压力场景间切换，联动更新达标概率、网络风险、额度、利率、RAROC 和贷后建议。

## 2. 功能范围

### 企业端（Vue）

- 转型账户：企业基线、碳强度、行业参考、年度目标。
- 转型路径：项目预算、资金需求、执行进度和里程碑。
- 真实转型诊断：LMDI 活动、能效、能源结构效应分解。
- 转型可信度：达标概率、可信度分数/等级、TOP5 SHAP 驱动因素。
- 融资方案：基础额度、转型支持、风险扣减、建议额度及观察期条件。

### 银行端（Vue）

- 园区驾驶舱：企业、项目、授信敞口和预警概览。
- 企业智能评估：传统授信摘要、转型可信度、数据质量和异常提示。
- 园区关联风险：自身/一阶/二阶风险及 TOP3 传播路径。
- 情景压力测试：天然气价格冲击联动三大引擎重新计算。
- 动态融资决策：额度瀑布、建议利率、RAROC 校验和管理动作。
- 防漂绿预警：资金、项目、绩效与数据异常的分级人工核验清单。

## 3. 算法链

### 3.1 LMDI 真实减排识别

按企业相邻观察期，将碳排放变化分解为：

```text
Delta C = Delta C_activity + Delta C_intensity + Delta C_energy
```

实现使用加法 LMDI：活动效应刻画产量变化，能效效应刻画单位产出的能源需求变化，能源结构效应包含能源占比和排放因子的变化。原型不采集企业核心工艺参数，因此暂不单列工艺效应。

### 3.2 转型目标达标概率与解释

LightGBM 基于模拟企业样本训练二分类模型：

```text
P_target = P(未来 12 个月按计划完成转型目标 | X)
Transition Score = 1000 * P_target
```

特征覆盖真实减排、项目执行、资金行为、经营承受力和数据可信度。SHAP `TreeExplainer` 输出单企业 TOP5 正负驱动因素。比赛数据使用固定随机种子生成，并保留独立测试集指标，结果不宣称代表真实业务准确率。

### 3.3 异常检测与数据可信度

Isolation Forest 对能耗、产量、项目进度和付款等特征做无监督异常检测：

```text
Anomaly Score increases -> Q_data decreases -> transition support decreases
```

异常分数只用于降低数据可信度或触发人工复核，不直接认定企业漂绿或造假。

### 3.4 园区两阶风险传播

企业、供应商、客户和共享能源设施构成加权有向网络。边 `source -> target` 表示源节点风险会影响目标节点：

```text
r0_i = a * (1 - P_target_i) + b * ShockSensitivity_i
r* = clip(r0 + lambda * W*r0 + lambda^2 * W^2*r0, 0, 1)
```

系统保留自身、一阶、二阶风险贡献和 TOP3 路径，仅传播两阶以保证可解释性。

### 3.5 动态融资与 RAROC

```text
L_transition = C_project * alpha * P_target * Q_data
L_network = (L_base + L_transition) * min(g_max, k * R_network)
L_final = L_base + L_transition - L_network

R_loan = R_base + RP_credit + RP_network - D_transition
RAROC = (loan_income - expected_loss - operating_cost) / risk_capital
```

若建议利率不满足演示 RAROC 阈值，系统逐步收回绩效优惠直至达到阈值或输出人工复核提示。

## 4. 技术栈与目录

- Python 3.10+ / FastAPI：算法 REST API
- Vue 3 / Vite：双终端单页应用
- npm：前端依赖与全栈开发命令
- pandas / NumPy：数据处理与 LMDI
- LightGBM / SHAP：预测与解释
- scikit-learn：异常检测和模型评估
- NetworkX：园区关系图与传播路径
- Plotly：业务图表

```text
.
├─ backend/
│  ├─ main.py                 # FastAPI 入口
│  └─ routers/                # 健康、元数据、驾驶舱和企业分析接口
├─ frontend/
│  ├─ src/                    # Vue 页面、组件、样式与 API 客户端
│  ├─ package.json
│  └─ vite.config.js          # 开发服务器与 API 代理
├─ services/
│  └─ analysis_service.py     # 应用服务与 API 数据整形
├─ carbon_finance/
│  ├─ config.py               # 演示参数与中文字段映射
│  ├─ data.py                 # 模拟数据加载
│  ├─ lmdi.py                 # 加法 LMDI
│  ├─ transition.py           # LightGBM、SHAP、异常检测
│  ├─ network.py              # 两阶风险传播与路径解释
│  ├─ finance.py              # 额度、利率和 RAROC
│  └─ pipeline.py             # 三引擎联动编排
├─ scripts/generate_demo_data.py
├─ data/                      # 固定种子生成的 CSV 演示数据
├─ docs/ARCHITECTURE.md       # 前后端与算法服务架构
├─ tests/                     # 核心公式与场景联动测试
├─ package.json               # 根 npm 全栈命令
├─ environment.yml
└─ requirements.txt
```

## 5. 运行

本项目按工作区约定使用 Conda 环境 `pytorch_env`。首次安装：

```powershell
conda activate pytorch_env
pip install -r requirements.txt
python scripts/generate_demo_data.py
npm run install:all
```

一条命令启动 FastAPI 与 Vue：

```powershell
conda activate pytorch_env
npm run dev
```

Vite 前端支持热更新；后端为保证 Windows 与模型运行稳定采用普通 Uvicorn 进程，修改 Python 后重新执行 `npm run dev`。

- Vue 前端：<http://127.0.0.1:5173>
- FastAPI 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

也可以分别运行：

```powershell
npm run dev:backend
npm run dev:frontend
```

运行后端测试与前端生产构建：

```powershell
conda activate pytorch_env
npm test
npm run build
```

## 6. 验收标准

- `pytest -q` 全部通过。
- 固定随机种子下可重复生成模拟数据并训练模型。
- Vue 页面可切换企业端/银行端、企业和正常/压力情景，无异常堆栈。
- FastAPI 的健康、园区驾驶舱和企业分析接口返回有效 JSON。
- LMDI 各效应之和与总排放变化在容差内一致。
- 模型真实使用 LightGBM 预测并输出 SHAP 解释，不使用前端硬编码概率。
- 网络风险由矩阵计算产生，可分解为自身、一阶和二阶贡献并追溯主要路径。
- 压力场景能联动改变达标概率、网络风险和融资建议。
- 所有关键结果标注“模拟演示/辅助决策”，不出现自动批贷或直接认定漂绿的表述。

## 7. 后续落地边界

真实落地需要完成企业授权、数据分级分类、接口审计、行业口径治理，并使用真实历史转型项目进行分行业训练、概率校准、时间滚动验证和模型风险审批。钢铁模型不能直接套用于化工等异质行业；银行现有基础授信与人工审批始终保留最终决策权。
