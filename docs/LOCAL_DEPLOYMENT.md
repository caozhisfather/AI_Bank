# 本地部署说明

部署日期：2026-10-22。当前工作区已从 `caozhisfather/AI_Bank` 的 `main` 分支拉取，基准提交为 `b9dfa82`。

## 访问

- 前端：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

服务仅监听本机地址。首次运行将演示数据迁入项目内 SQLite，后续工作台从数据库读取，无需安装外部数据库服务或配置模型 API 密钥。

## 当前环境

- macOS Apple Silicon，Node.js 24.18.1 / npm 11.16.0。
- Python 3.12.13，解释器为项目中的 `.venv/bin/python`。PyCharm 可选择该解释器。
- Python 依赖已按 `requirements.txt` 安装；前端依赖已安装并更新锁文件，`npm audit` 报告 0 项漏洞。
- `npm run dev:backend` 和 `npm test` 通过 `scripts/python.cjs` 自动使用 `.venv`，无需激活 Conda。

本机未安装 Homebrew，因此 OpenMP 运行库采用 conda-forge 的 `llvm-openmp 23.1.4`（`osx-arm64`）包，安装于 `.venv/lib/libomp.dylib`，许可证保存在 `.venv/lib/llvm-openmp-licenses/`。下载包的 SHA-256 已校验：

```text
cc6d67df56d4ea967e17d938d3108cdf7d971531350df9e7fc5e18cb89066a70
```

包地址：<https://conda.anaconda.org/conda-forge/osx-arm64/llvm-openmp-23.1.4-hdb3d66b_0.conda>。

LightGBM 的本地动态库已添加 `@loader_path/../../../..` 搜索路径并重新进行临时签名，使其能够从 `.venv/lib` 加载 OpenMP。这些环境文件均未纳入 Git。若删除 `.venv` 或重装 LightGBM，需要重新配置 OpenMP；安装了 Homebrew 的机器可使用 `brew install libomp`。

## 启动与停止

本次服务已经在后台启动，日志位于 `.codex_tmp/dev.log`，进程号记录于 `.codex_tmp/dev.pid`。

在项目根目录停止本次后台服务：

```bash
.venv/bin/python .codex_tmp/stop-dev.py
```

后续在项目根目录启动：

```bash
npm run dev
```

该命令同时启动前后端，并在终端持续输出日志；按 `Ctrl+C` 停止。已有服务运行时应先停止，避免端口冲突。`.codex_tmp` 是当前工作区的临时运行目录，不纳入 Git。

## 已完成验证

- `npm test`：23 项测试通过，覆盖数据入库、企业隔离、核验闭环和原有算法；测试使用临时数据库。
- `npm run build`：前端生产构建通过，产物位于 `frontend/dist/`。
- `npm audit --audit-level=low`：0 项漏洞。
- `uv pip check --python .venv/bin/python`：依赖兼容检查通过。
- 后端直连及前端代理：健康检查、元数据、园区驾驶舱、企业分析、Agent 工作流与历史记录接口正常；当前模拟数据为 36 家企业、正常情景及 5 类压力情景。
- 错误输入返回正确的 400 / 404 状态码。
- 浏览器可通过双端登录页进入银行或企业工作台，使用企业评估、压力测试和风险图谱页面。银行端保留六个核心页面，Agent 工作流独立页面已移除，相关后端接口仍可通过 API 文档调用。

测试中存在不影响通过的 pytest 配置提示；部分并发请求可能输出 SHAP 提示，分析接口仍返回正常结果。

## 压缩包合并记录

2026-10-22 已合并 `/Users/a11111/Downloads/AI_bank.tar` 中 `工行杯/` 目录的源码、模拟数据、导入模板、数据库历史及文档、演示材料。压缩包内的 `node_modules`、构建产物、Python 缓存和临时文件未覆盖本机环境。

- 本地跨平台 Python 启动器和已修复漏洞的 npm 锁文件保持有效。
- 已安装新增的 multipart、LangChain、LangGraph 和 DeepAgents 依赖，并遵循压缩包中 Pydantic 的版本约束。
- 压缩包中的 SQLite 数据库包含 20 条数据集、15 条工作流；测试产生的数据已从运行数据库移除，原始历史完整保留。
- 默认使用离线确定性 Agent 流程。在线 DeepAgents 监督需要另行配置 `DEEPAGENT_MODEL` 与 `OPENAI_API_KEY`，本次未启用在线模型。
- 合并前源码及本地部署文件已备份到 `.codex_tmp/before-archive-merge-20261022.tar.gz`；逐文件合并清单位于 `.codex_tmp/archive-merge-manifest.json`。

2026-10-23 起：银行端 `bank_demo`，企业 A `company_demo`，企业 F `company_F`，默认密码均为 `demo123`。可通过后端环境变量 `PLATFORM_DEMO_PASSWORD` 修改。后端会校验会话、角色及企业归属。银行端第六页为“审核任务清单”，企业端新增“数据接入与补充材料”。接口与演示步骤见 [企业接入与银行核验闭环](ENTERPRISE_REVIEW_WORKFLOW.md)。
