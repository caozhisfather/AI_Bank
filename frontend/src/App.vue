<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getAnalysis, getDashboard, getMetadata } from './api'
import MetricCard from './components/MetricCard.vue'
import BarList from './components/BarList.vue'

const terminal = ref('银行端')
const activeTab = ref('园区驾驶舱')
const metadata = ref(null)
const dashboard = ref(null)
const analysis = ref(null)
const companyId = ref('A')
const scenario = ref('正常情景')
const loading = ref(true)
const error = ref('')

const bankTabs = ['园区驾驶舱', '智能评估', '关联风险', '压力测试', '融资决策', '贷后预警']
const companyTabs = ['转型账户', '转型路径', '真实减排', '转型可信度', '融资方案']
const tabs = computed(() => terminal.value === '银行端' ? bankTabs : companyTabs)
const company = computed(() => analysis.value?.company || {})
const normal = computed(() => analysis.value?.comparison.normal || {})
const stress = computed(() => analysis.value?.comparison.stress || {})
const currentMeta = computed(() => metadata.value?.companies.find(x => x.company_id === companyId.value) || {})
const pct = v => `${(Number(v || 0) * 100).toFixed(1)}%`
const money = v => `${Math.round(Number(v || 0)).toLocaleString()} 万元`
const delta = (a, b, suffix = '%') => suffix === '%' ? `${((a - b) * 100).toFixed(1)}%` : `${Math.round(a - b)} 万元`

const lmdiItems = computed(() => analysis.value ? [
  { label: '活动/产量', value: analysis.value.lmdi.activity },
  { label: '能效', value: analysis.value.lmdi.efficiency },
  { label: '能源结构', value: analysis.value.lmdi.energy_structure }
] : [])
const riskItems = computed(() => dashboard.value?.companies.map(x => ({
  label: x.company_name, value: x.network_risk
})) || [])

async function load() {
  loading.value = true; error.value = ''
  try {
    const [d, a] = await Promise.all([getDashboard(scenario.value), getAnalysis(companyId.value, scenario.value)])
    dashboard.value = d; analysis.value = a
  } catch (e) { error.value = e.message } finally { loading.value = false }
}

function switchTerminal(value) {
  terminal.value = value
  activeTab.value = value === '银行端' ? bankTabs[0] : companyTabs[0]
}

watch([companyId, scenario], load)
onMounted(async () => {
  try { metadata.value = await getMetadata(); await load() }
  catch (e) { error.value = e.message; loading.value = false }
})
</script>

<template>
  <div class="app-shell">
    <aside>
      <div class="brand"><span>ICBC</span><div><b>工银·碳跃智衡</b><small>可信转型融资决策平台</small></div></div>
      <label>工作台</label>
      <div class="terminal-switch"><button v-for="x in ['银行端','企业端']" :class="{active:terminal===x}" @click="switchTerminal(x)">{{ x }}</button></div>
      <label>评估企业</label>
      <select v-model="companyId"><option v-for="x in metadata?.companies" :value="x.company_id">{{ x.company_name }} · {{ x.industry }}</option></select>
      <label>分析情景</label>
      <select v-model="scenario"><option v-for="x in metadata?.scenarios">{{ x }}</option></select>
      <nav><button v-for="tab in tabs" :class="{active:activeTab===tab}" @click="activeTab=tab"><i></i>{{ tab }}</button></nav>
      <footer>算法原型 · 模拟数据 · 辅助决策</footer>
    </aside>

    <main>
      <header><div><small>TRANSITION FINANCE / 2026</small><h1>碳跃智衡</h1><p>{{ currentMeta.company_name }} · {{ currentMeta.industry }} · {{ scenario }}</p></div><span class="online"><i></i>模型服务在线</span></header>
      <div class="disclaimer">{{ metadata?.disclaimer }}</div>
      <div v-if="error" class="error">{{ error }}。请确认 Python 后端已启动。</div>
      <div v-if="loading" class="loading"><i></i>正在调用三引擎计算链...</div>

      <template v-else-if="analysis">
        <section class="metrics">
          <MetricCard label="转型达标概率" :value="pct(company.p_target)" :delta="scenario!=='正常情景'?delta(company.p_target,normal.p_target):''" danger />
          <MetricCard label="转型可信度" :value="`${company.transition_score} 分`" />
          <MetricCard label="园区关联风险" :value="pct(company.network_risk)" :delta="scenario!=='正常情景'?delta(company.network_risk,normal.network_risk):''" danger />
          <MetricCard label="建议融资额度" :value="money(company.final_limit)" :delta="scenario!=='正常情景'?delta(company.final_limit,normal.final_limit,'万元'):''" />
          <MetricCard label="演示 RAROC" :value="pct(company.raroc)" />
        </section>

        <section class="workspace">
          <template v-if="activeTab==='园区驾驶舱'">
            <h2>示范园区运行概览</h2><p class="sub">企业转型、信贷敞口与风险预警的统一视图</p>
            <div class="summary-grid">
              <div><span>接入企业</span><b>{{ dashboard.summary.company_count }} 家</b></div>
              <div><span>基础授信敞口</span><b>{{ money(dashboard.summary.base_exposure) }}</b></div>
              <div><span>转型项目需求</span><b>{{ money(dashboard.summary.project_need) }}</b></div>
              <div><span>关注及以上预警</span><b>{{ dashboard.summary.alerts }} 家</b></div>
            </div>
            <div class="table-wrap"><table><thead><tr><th>企业</th><th>行业</th><th>达标概率</th><th>关联风险</th><th>建议额度</th><th>预警</th></tr></thead><tbody><tr v-for="x in dashboard.companies" @click="companyId=x.company_id"><td><b>{{x.company_name}}</b></td><td>{{x.industry}}</td><td>{{pct(x.p_target)}}</td><td>{{pct(x.network_risk)}}</td><td>{{money(x.final_limit)}}</td><td><span class="tag">{{x.warning_level}}</span></td></tr></tbody></table></div>
          </template>

          <template v-else-if="['智能评估','真实减排'].includes(activeTab)">
            <h2>LMDI 真实转型诊断</h2><p class="sub">识别排放变化来自产量、能效还是能源结构</p>
            <div class="two-columns"><div class="panel"><BarList :items="lmdiItems" label-key="label" value-key="value" signed :formatter="v=>`${v>0?'+':''}${v.toFixed(2)}`" /></div><div class="insight"><span>本期总排放变化</span><strong>{{ analysis.lmdi.total_change.toFixed(2) }}</strong><p>能效与能源结构效应由真实能耗数据分解得出，避免将减产形成的表观减排误判为高质量转型。</p></div></div>
          </template>

          <template v-else-if="['转型可信度'].includes(activeTab)">
            <h2>未来 12 个月转型可信度</h2><p class="sub">LightGBM 预测与 SHAP 单企业解释</p>
            <div class="panel"><BarList :items="analysis.shap" label-key="label" value-key="contribution" signed :formatter="v=>v.toFixed(3)" /></div><p class="footnote">模拟测试集 AUC {{ analysis.model_auc.toFixed(3) }}，仅用于验证算法流程。</p>
          </template>

          <template v-else-if="activeTab==='关联风险'">
            <h2>园区两阶关联风险</h2><p class="sub">自身风险 + 一阶直接传播 + 二阶间接传播</p>
            <div class="two-columns"><div class="panel"><BarList :items="riskItems" label-key="label" value-key="value" :formatter="pct" /></div><div class="paths"><h3>TOP 风险传播路径</h3><div v-for="(x,i) in analysis.risk_paths"><em>0{{i+1}}</em><span>{{x.path}}</span><b>{{pct(x.contribution)}}</b></div></div></div>
          </template>

          <template v-else-if="activeTab==='压力测试'">
            <h2>正常 / 压力情景对比</h2><p class="sub">天然气价格冲击沿模型链逐层传导</p>
            <div class="scenario-flow"><div><span>外部冲击</span><b>天然气 +30%</b></div><i>→</i><div><span>达标概率</span><b>{{pct(normal.p_target)}} → {{pct(stress.p_target)}}</b></div><i>→</i><div><span>园区风险</span><b>{{pct(normal.network_risk)}} → {{pct(stress.network_risk)}}</b></div><i>→</i><div><span>建议额度</span><b>{{money(normal.final_limit)}} → {{money(stress.final_limit)}}</b></div></div>
          </template>

          <template v-else-if="['融资决策','融资方案'].includes(activeTab)">
            <h2>风险收益约束的动态融资</h2><p class="sub">基础授信 + 转型支持 − 网络风险扣减</p>
            <div class="finance-flow"><div><span>基础授信</span><b>{{money(company.base_limit)}}</b></div><i>+</i><div class="positive"><span>转型支持</span><b>{{money(company.transition_support)}}</b></div><i>−</i><div class="negative"><span>风险扣减</span><b>{{money(company.network_deduction)}}</b></div><i>=</i><div class="total"><span>建议额度</span><b>{{money(company.final_limit)}}</b></div></div><div class="decision"><span class="tag">{{company.warning_level}}</span><b>建议利率 {{pct(company.suggested_rate)}}</b><p>{{company.action}}。正式授信及合同调整须经银行人工审批。</p></div>
          </template>

          <template v-else-if="activeTab==='贷后预警'">
            <h2>防漂绿与贷后人工核验</h2><p class="sub">异常模型只提示数据组合异常，不直接认定漂绿或造假</p>
            <div class="table-wrap"><table><thead><tr><th>企业</th><th>异常分数</th><th>数据可信度</th><th>预警</th><th>建议动作</th></tr></thead><tbody><tr v-for="x in dashboard.companies"><td><b>{{x.company_name}}</b></td><td>{{pct(x.anomaly_score)}}</td><td>{{pct(x.data_quality)}}</td><td><span class="tag">{{x.warning_level}}</span></td><td>{{x.action}}</td></tr></tbody></table></div>
          </template>

          <template v-else-if="activeTab==='转型账户'">
            <h2>企业转型账户</h2><div class="summary-grid"><div><span>当前碳强度</span><b>{{company.carbon_intensity.toFixed(3)}}</b></div><div><span>目标碳强度</span><b>{{company.target_intensity.toFixed(3)}}</b></div><div><span>数据可信度</span><b>{{pct(company.data_quality)}}</b></div><div><span>异常分数</span><b>{{pct(company.anomaly_score)}}</b></div></div>
          </template>

          <template v-else-if="activeTab==='转型路径'">
            <h2>{{analysis.project.name}}</h2><p class="sub">转型项目里程碑与资金执行</p><div class="summary-grid"><div><span>项目融资需求</span><b>{{money(company.project_need)}}</b></div><div><span>执行进度</span><b>{{pct(analysis.project.progress)}}</b></div><div><span>自有资金到位</span><b>{{pct(analysis.project.own_fund_arrival)}}</b></div><div><span>资金用途一致</span><b>{{pct(analysis.project.fund_usage_match)}}</b></div></div><div class="progress"><i :style="{width:pct(analysis.project.progress)}"></i></div><p class="footnote">当前里程碑延迟 {{analysis.project.milestone_delay_days}} 天。</p>
          </template>
        </section>
      </template>
    </main>
  </div>
</template>
