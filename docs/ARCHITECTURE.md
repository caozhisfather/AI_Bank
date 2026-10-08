# 系统架构

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
        +-- LMDI + LightGBM/SHAP + Isolation Forest
        +-- 两阶园区风险传播
        +-- 动态额度、定价与 RAROC
        |
        v
CSV 模拟数据底座
```

前端不保存或计算模型结论，只负责业务展示与交互。后端路由层只处理 HTTP 协议，服务层负责结果整形，`carbon_finance` 保留可独立测试的纯算法模块。
