<script setup>
defineProps({ section: { type: String, required: true } })
defineEmits(['open-workbench'])

const pages = {
  '转型金融': {
    en: 'TRANSITION FINANCE',
    title: '以可信数据识别真实转型价值',
    lead: '围绕高碳行业企业的转型路径、减排绩效和融资需求，形成从识别、评价到授信建议的完整决策链。',
    stats: [['3 类', '核心算法引擎'], ['12 个月', '达标预测窗口'], ['全流程', '证据链留痕']],
    columns: [
      ['转型识别', '通过 LMDI 分解识别产量、能效与能源结构贡献，区分真实减排和表观减排。'],
      ['可信评价', '通过产量、能效、能源结构与工艺四因素分析减排来源，展示未来12个月的转型达标概率。'],
      ['融资匹配', '在风险收益约束下动态测算融资额度、建议利率和差异化管理措施。']
    ],
    process: ['企业转型建档', '碳绩效诊断', '转型可信评估', '融资方案生成']
  },
  '园区风控': {
    en: 'INDUSTRIAL PARK RISK',
    title: '看清单户风险之外的园区关联影响',
    lead: '以供应链、担保和资金往来关系构建园区风险网络，识别一阶与二阶传播路径，支持组合风险管理。',
    stats: [['2 阶', '风险传播网络'], ['多情景', '压力测试'], ['可追溯', '关键风险路径']],
    columns: [
      ['风险图谱', '统一展示园区企业、关系边与风险敞口，定位核心节点和风险聚集区域。'],
      ['传播测算', '量化单户风险经供应链和担保关系向园区传导的方向、强度与贡献。'],
      ['动态预警', '结合异常检测和情景冲击，形成关注、预警、阻断三级管理建议。']
    ],
    process: ['关系数据接入', '网络风险计算', '冲击情景推演', '预警处置闭环']
  },
  '产品服务': {
    en: 'PRODUCTS & SERVICES',
    title: '面向转型项目的差异化金融服务',
    lead: '将转型成效、项目进度和风险成本转化为可执行的额度、定价与贷后管理建议，服务银行和企业双端。',
    stats: [['银行端', '组合决策工作台'], ['企业端', '转型账户服务'], ['HITL', '人工审批收口']],
    columns: [
      ['转型融资评估', '形成转型项目画像、资金需求核验、额度测算和风险收益分析。'],
      ['园区组合管理', '聚合园区敞口、预警等级和网络风险，支持名单制与情景化管理。'],
      ['贷后持续监测', '跟踪里程碑、资金用途与减排表现，对数据异常发起人工核验。']
    ],
    process: ['业务申请', '智能尽调', '协同审查', '人工审批与贷后']
  },
  '平台介绍': {
    en: 'PLATFORM OVERVIEW',
    title: '碳数据、风险模型与智能协同的一体化平台',
    lead: '“碳跃智衡”是面向转型金融场景的决策支持原型，以可解释算法为核心，以多智能体协作为业务编排方式。',
    stats: [['Vue + FastAPI', '前后端分离'], ['LangGraph', '状态图编排'], ['可解释', '算法与证据输出']],
    columns: [
      ['数据基础层', '接入企业经营、能耗排放、项目、授信和园区关系数据并执行质量校验。'],
      ['模型决策层', '集成 LMDI、可信度预测、异常检测、网络传播及 RAROC 约束算法。'],
      ['智能协同层', '多个专业 Agent 分工审阅计算结果，通过状态图形成可追溯的决策轨迹。']
    ],
    process: ['数据治理', '算法计算', 'Agent 协同', '证据归档与人工决策']
  }
}
</script>

<template>
  <main class="portal-page">
    <div class="portal-inner">
      <div class="breadcrumb"><button @click="$emit('open-workbench')">首页</button><i>/</i><b>{{ section }}</b></div>
      <section class="portal-hero">
        <div class="portal-copy">
          <small>{{ pages[section].en }} / 2026</small>
          <h1>{{ pages[section].title }}</h1>
          <p>{{ pages[section].lead }}</p>
          <button class="primary-action" @click="$emit('open-workbench')">进入业务工作台 <span>→</span></button>
        </div>
        <div class="portal-stats">
          <div v-for="item in pages[section].stats" :key="item[1]"><strong>{{ item[0] }}</strong><span>{{ item[1] }}</span></div>
        </div>
      </section>

      <section class="portal-section">
        <div class="section-heading"><div><small>CORE CAPABILITIES</small><h2>核心能力</h2></div><p>围绕转型金融业务全流程构建标准化能力组件</p></div>
        <div class="capability-grid">
          <article v-for="(item, index) in pages[section].columns" :key="item[0]">
            <em>0{{ index + 1 }}</em><h3>{{ item[0] }}</h3><p>{{ item[1] }}</p><button @click="$emit('open-workbench')">查看工作台 <span>→</span></button>
          </article>
        </div>
      </section>

      <section class="process-band">
        <div><small>BUSINESS PROCESS</small><h2>业务流程</h2></div>
        <ol><li v-for="(item,index) in pages[section].process" :key="item"><em>{{ index + 1 }}</em><span>{{ item }}</span></li></ol>
      </section>
      <footer class="site-footer"><span>工银“碳跃智衡”可信转型融资决策平台</span><span>模拟数据 · 辅助决策 · 人工审批</span><span>© 2026 金融科技创新原型</span></footer>
    </div>
  </main>
</template>
