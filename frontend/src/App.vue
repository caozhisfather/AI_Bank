<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { getAnalysis, getMetadata, logoutSession, setAccessToken } from './api'
import MetricCard from './components/MetricCard.vue'
import PortalPage from './components/PortalPage.vue'
import LoginGate from './components/LoginGate.vue'
import ParkRiskWorkspace from './components/ParkRiskWorkspace.vue'
import RarocComparison from './components/RarocComparison.vue'
import FinancingEquation from './components/FinancingEquation.vue'
import EmissionAttribution from './components/EmissionAttribution.vue'
import CredibilityMetric from './components/CredibilityMetric.vue'
import ReviewWorkspace from './components/ReviewWorkspace.vue'
import EnterpriseData from './components/EnterpriseData.vue'
import PredictionFactors from './components/PredictionFactors.vue'
import OperatingProfile from './components/OperatingProfile.vue'

const portalSection = ref('业务工作台')
const terminal = ref('银行端')
const activeTab = ref('转型可信度评价')
const metadata = ref(null)
const analysis = ref(null)
const companyId = ref('A')
const scenario = ref('正常情景')
const loading = ref(true)
const analysisUpdating = ref(false)
const error = ref('')
const session = ref(null)
const credibilitySection = ref(null)
const today = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const portalSections = ['业务工作台', '转型金融', '园区风控', '产品服务', '平台介绍']

const bankTabs = ['转型可信度评价', '园区风险分析', '融资决策', '审核任务清单']
const companyTabs = ['转型账户', '转型路径', '真实减排', '转型可信度', '融资方案', '数据接入与补充材料']
const tabs = computed(() => terminal.value === '银行端' ? bankTabs : companyTabs)
const company = computed(() => analysis.value?.company || {})
const normal = computed(() => analysis.value?.comparison.normal || {})
const stress = computed(() => analysis.value?.comparison.stress || {})
const selectedScenario = computed(() => analysis.value?.comparison.selected || {})
const scenarioMeta = computed(() => metadata.value?.scenario_catalog?.find(x => x.name === scenario.value) || {})
const currentMeta = computed(() => metadata.value?.companies.find(x => x.company_id === companyId.value) || {})
const pct = v => `${(Number(v || 0) * 100).toFixed(1)}%`
const money = v => `${Math.round(Number(v || 0)).toLocaleString()} 万元`
const delta = (a, b, suffix = '%') => suffix === '%' ? `${((a - b) * 100).toFixed(1)}%` : `${Math.round(a - b)} 万元`
const isOperating = computed(() => company.value.evaluation_model==='operating')
const tabTitle = tab => isOperating.value&&['转型可信度评价','转型可信度'].includes(tab)?'运行风险画像':tab
const isAssessment = computed(() => ['转型可信度评价', '转型可信度'].includes(activeTab.value))

let loadRevision = 0
let signingIn = false
async function load(silent = false) {
  if (!session.value) return
  const revision = ++loadRevision
  if (!silent) loading.value = true
  error.value = ''
  analysisUpdating.value = true
  try {
    const a = await getAnalysis(companyId.value, scenario.value)
    if (revision === loadRevision && session.value) analysis.value = a
  } catch (e) { if (revision === loadRevision) error.value = e.message } finally { if (revision === loadRevision) { loading.value = false; analysisUpdating.value = false } }
}

function switchTerminal(value) {
  terminal.value = value
  activeTab.value = value === '银行端' ? bankTabs[0] : companyTabs[0]
}

async function login(payload) {
  signingIn = true
  session.value = payload
  switchTerminal(payload.role)
  companyId.value = payload.company_id || 'A'
  scenario.value = '正常情景'
  try {
    const info = await getMetadata()
    if (session.value?.token !== payload.token) return
    metadata.value = info
    await load()
  }
  catch (e) { error.value = e.message; loading.value = false }
  finally { if (session.value?.token === payload.token) signingIn = false }
}

function clearSession() {
  loadRevision++
  signingIn = false
  setAccessToken('')
  session.value = null
  metadata.value = null; analysis.value = null
  portalSection.value = '业务工作台'
}
async function logout() { try { await logoutSession() } finally { clearSession() } }

function openPortal(section) {
  portalSection.value = section
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function showCredibility() {
  activeTab.value = terminal.value === '银行端' ? '转型可信度评价' : '转型可信度'
  await nextTick()
  credibilitySection.value?.focus({ preventScroll: true })
  credibilitySection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch([companyId, scenario], () => { if (!signingIn) load(activeTab.value==='园区风险分析' && Boolean(analysis.value)) })
onMounted(() => window.addEventListener('session-expired', clearSession))
onBeforeUnmount(() => window.removeEventListener('session-expired', clearSession))
</script>

<template>
  <LoginGate v-if="!session" @login="login" />
  <div v-else class="website">
    <div class="site-header">
      <div class="site-brand"><span class="brand-seal">工</span><div><b>工银·碳跃智衡</b><small>ICBC CARBON TRANSITION INTELLIGENCE</small></div></div>
      <nav class="site-nav"><button v-for="item in portalSections" :key="item" :class="{active:portalSection===item}" @click="openPortal(item)">{{ item }}</button></nav>
      <div class="institution"><span>{{ session.account }} · {{ session.role }}</span><button class="logout-button" @click="logout">退出</button><b>{{ today }}</b></div>
    </div>
    <PortalPage v-if="portalSection!=='业务工作台'" :section="portalSection" @open-workbench="openPortal('业务工作台')" />
  <div v-else class="app-shell">
    <aside>
      <div class="brand"><span>TF</span><div><b>转型金融工作台</b></div></div>
      <label>工作台</label>
      <div class="terminal-identity"><span>{{ terminal === '银行端' ? '客户经理 / 风控人员' : '园区企业用户' }}</span><b>{{ session.account }}</b></div>
      <label>评估企业</label>
      <select v-model="companyId"><option v-for="x in metadata?.companies" :value="x.company_id">{{ x.company_name }} · {{ x.industry }}</option></select>
      <label v-if="activeTab!=='园区风险分析'">分析情景</label>
      <select v-if="activeTab!=='园区风险分析'" v-model="scenario"><option v-for="x in metadata?.scenarios">{{ x }}</option></select>
      <nav><button v-for="tab in tabs" :class="{active:activeTab===tab}" @click="activeTab=tab"><i></i>{{ tabTitle(tab) }}</button></nav>
    </aside>

    <main>
      <div class="workbench-banner">
      <div class="breadcrumb"><span>首页</span><i>/</i><span>{{ terminal }}</span><i>/</i><b>{{ tabTitle(activeTab) }}</b></div>
      <header class="page-hero"><div><h1>{{ tabTitle(activeTab) }}</h1><p v-if="activeTab!=='审核任务清单'">{{ currentMeta.company_name }} · {{ currentMeta.industry }} · {{ scenario }}</p></div><div class="hero-meta"><span class="online"><i></i>模型服务在线</span><span class="version">模型版本 CTI 1.0</span></div></header>
      </div>
      <div v-if="error" class="error">{{ error }}。请确认 Python 后端已启动。</div>
      <div v-if="loading" class="loading"><i></i>正在调用三引擎计算链...</div>

      <template v-else-if="analysis">
        <section class="metrics">
          <CredibilityMetric v-if="!isOperating" :attribution="analysis.lmdi" @show-evidence="showCredibility" />
          <MetricCard v-if="isOperating" label="主要商品或服务" :value="company.product" />
          <MetricCard class="risk-metric" label="园区综合风险" :value="pct(company.network_risk)" :delta="analysis.scenario!=='正常情景'?`${((company.network_risk-normal.network_risk)*100).toFixed(2)}个百分点`:''" danger />
          <MetricCard class="financing-metric" label="建议融资额度" :value="isOperating?'未适配融资模型':money(company.final_limit)" :delta="!isOperating&&analysis.scenario!=='正常情景'?delta(company.final_limit,normal.final_limit,'万元'):''" />
        </section>

        <section v-if="isAssessment&&!isOperating" ref="credibilitySection" class="workspace attribution-workspace" tabindex="-1" aria-label="减排归因分析">
          <h2>减排归因分析</h2>
          <EmissionAttribution :result="analysis.lmdi" />
        </section>
        <section v-if="isAssessment&&!isOperating" class="workspace probability-workspace" aria-label="未来12个月的转型达标概率">
          <h2>未来12个月的转型达标概率</h2>
          <p class="assessment-probability" aria-label="达标概率">{{ pct(company.p_target) }}</p>
          <PredictionFactors :explanation="analysis.shap_probability" />
        </section>

        <section v-if="isOperating&&!['园区风险分析','审核任务清单','数据接入与补充材料'].includes(activeTab)" class="workspace"><OperatingProfile :analysis="analysis" /></section>
        <section v-else-if="!isAssessment" class="workspace">
          <template v-if="activeTab==='真实减排'">
            <h2>减排归因分析</h2>
            <EmissionAttribution :result="analysis.lmdi" />
          </template>

          <template v-else-if="activeTab==='园区风险分析'">
            <ParkRiskWorkspace :analysis="analysis" :scenario="scenario" :scenarios="metadata?.scenarios" :scenario-catalog="metadata?.scenario_catalog" :updating="analysisUpdating" @scenario="scenario=$event" @select="companyId=$event" />
          </template>

          <template v-else-if="['融资决策','融资方案'].includes(activeTab)">
            <h2>风险收益约束的动态融资</h2><p class="sub">基础授信 + 转型支持 − 网络风险扣减</p>
            <FinancingEquation :decision="company" /><div class="decision"><span class="tag">{{company.warning_level}}</span><b>建议利率 {{pct(company.suggested_rate)}}</b><p>{{company.action}}。正式授信及合同调整须经银行人工审批。</p></div>
            <RarocComparison :decision="company" />
          </template>

          <template v-else-if="activeTab==='审核任务清单'">
            <ReviewWorkspace :user="session" :company-id="companyId" :version-id="analysis.data_version.id" @changed="load(true)" />
          </template>

          <template v-else-if="activeTab==='数据接入与补充材料'">
            <EnterpriseData :user="session" :company-id="companyId" :version-id="analysis.data_version.id" @changed="load(true)" />
          </template>

          <template v-else-if="activeTab==='转型账户'">
            <h2>企业转型账户</h2><div class="summary-grid"><div><span>当前碳强度</span><b>{{company.carbon_intensity.toFixed(3)}}</b></div><div><span>目标碳强度</span><b>{{company.target_intensity.toFixed(3)}}</b></div><div><span>数据可信度</span><b>{{pct(company.data_quality)}}</b></div><div><span>原始异常分数</span><b>{{pct(company.anomaly_score)}}</b></div></div><p class="footnote">数据 V{{ analysis.data_version.version }} · {{ analysis.data_version.period }} · {{ analysis.data_version.source }}{{company.anomaly_reviewed ? ' · 当前版本组合异常已核验合理' : ''}}</p><button class="review-secondary" @click="activeTab='数据接入与补充材料'">查看接口接入与补充材料</button>
          </template>

          <template v-else-if="activeTab==='转型路径'">
            <h2>{{analysis.project.name}}</h2><p class="sub">转型项目里程碑与资金执行</p><div class="summary-grid"><div><span>项目融资需求</span><b>{{money(company.project_need)}}</b></div><div><span>执行进度</span><b>{{pct(analysis.project.progress)}}</b></div><div><span>自有资金到位</span><b>{{pct(analysis.project.own_fund_arrival)}}</b></div><div><span>资金用途一致</span><b>{{pct(analysis.project.fund_usage_match)}}</b></div></div><div class="progress"><i :style="{width:pct(analysis.project.progress)}"></i></div><p class="footnote">当前里程碑延迟 {{analysis.project.milestone_delay_days}} 天。</p>
            <div class="evidence-strip"><b>转型证据链</b><span>设备采购合同</span><span>项目里程碑</span><span>贷款支付凭证</span><span>月度能耗绩效</span></div>
          </template>
        </section>
      </template>
      <footer class="site-footer"><span>工银“碳跃智衡”可信转型融资决策平台</span><span>模拟数据 · 辅助决策 · 人工审批</span><span>© 2026 金融科技创新原型</span></footer>
    </main>
  </div>
  </div>
</template>
