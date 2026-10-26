<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getAnalysisWorkflows, runAnalysisWorkflow } from '../api'
import EmissionAttribution from './EmissionAttribution.vue'
import PredictionFactors from './PredictionFactors.vue'
import FinancingEquation from './FinancingEquation.vue'

const props = defineProps({ companyId: String, scenario: String, analysis: Object })
const emit = defineEmits(['completed'])
const definitions = [
  { id: 'data', name: '读取与校验', method: '版本化业务数据', description: '读取后台已入库的企业数据，锁定本次计算版本。' },
  { id: 'lmdi', name: '减排归因', method: 'LMDI 分解', description: '分解排放变化来自产量、能效、能源结构及可用的工艺明细。' },
  { id: 'transition', name: '预测与识别', method: 'LightGBM / SHAP / Isolation Forest', description: '预测目标兑现概率，解释影响因素，并识别需人工核验的异常组合。' },
  { id: 'network', name: '关联风险', method: '一阶、二阶风险传播', description: '计算企业自身风险及园区关联传入影响，定位主要传播路径。' },
  { id: 'finance', name: '融资测算', method: '额度 / 定价 / RAROC', description: '将转型支持和园区风险映射到额度、利率，并校验风险收益底线。' },
  { id: 'stress', name: '压力对照', method: '正常与燃气价格压力情景', description: '分别计算两种情景，比较达标概率、关联风险和融资建议。' },
  { id: 'review', name: '核验留痕', method: '任务生成与版本审计', description: '根据实际入库事实生成核验任务，保留本次计算记录。' },
]
const states = ref({}), logs = ref([]), selected = ref('data'), running = ref(false)
const error = ref(''), runId = ref(''), totalMs = ref(null), stale = ref(false), history = ref([])
const active = computed(() => definitions.find(step => step.id === selected.value))
const stepState = computed(() => states.value[selected.value] || {})
const result = computed(() => stepState.value.result)
const dataVersion = computed(() => states.value.data?.result?.data_version)
const doneCount = computed(() => definitions.filter(step => states.value[step.id]?.status === 'completed').length)
const phaseResult = id => states.value[id]?.result
const pct = value => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
const amount = value => Number.isFinite(value) ? `${Math.round(value).toLocaleString('zh-CN')} 万元` : '—'
const number = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: 3 }) : '—'
const duration = value => value == null ? '—' : value < 1000 ? `${value.toFixed(0)} ms` : `${(value / 1000).toFixed(2)} s`
const statusLabel = value => ({ running: '计算中', completed: '已完成', failed: '失败', cancelled: '已取消' })[value] || '待运行'
const energyName = value => ({ coal: '煤炭', gas: '天然气', natural_gas: '天然气', electricity: '电力' })[value] || value
const taskStatus = value => ({ awaiting_material: '待补充材料', pending_review: '待银行核验', resolved: '已结案', returned: '已退回', tracking: '持续跟踪', superseded: '历史版本' })[value] || value
let controller = null, generation = 0

async function refreshHistory() {
  const id = props.companyId
  try {
    const response = await getAnalysisWorkflows(id)
    if (props.companyId === id) history.value = response.items.slice(0, 5)
  } catch { /* A history failure must not hide the live calculation. */ }
}
function receive(event) {
  if (event.type === 'started') runId.value = event.workflow_id
  if (event.type === 'stage') {
    states.value = { ...states.value, [event.stage]: { ...states.value[event.stage], ...event } }
    if (event.status === 'running') selected.value = event.stage
  }
  if (event.type === 'error') {
    states.value = { ...states.value, [event.stage]: { ...states.value[event.stage], status: 'failed' } }
  }
  if (event.type === 'completed') {
    totalMs.value = event.duration_ms
    stale.value = !event.snapshot_is_current
    selected.value = 'finance'
  }
  logs.value.push(event)
}
async function run() {
  if (running.value) return
  const currentGeneration = ++generation
  controller = new AbortController()
  states.value = {}; logs.value = []; runId.value = ''; totalMs.value = null; error.value = ''; stale.value = false
  selected.value = 'data'; running.value = true
  try {
    await runAnalysisWorkflow(props.companyId, props.scenario, event => {
      if (generation === currentGeneration) receive(event)
    }, controller.signal)
    if (generation === currentGeneration) { emit('completed'); await refreshHistory() }
  } catch (e) {
    if (generation === currentGeneration) {
      error.value = e.name === 'AbortError' ? '已停止本次运行，可以重新开始。' : e.message
      for (const step of definitions) {
        if (states.value[step.id]?.status === 'running') states.value[step.id].status = e.name === 'AbortError' ? 'cancelled' : 'failed'
      }
    }
  } finally {
    if (generation === currentGeneration) running.value = false
  }
}
function reset() {
  generation++; controller?.abort(); running.value = false
  states.value = {}; logs.value = []; history.value = []; totalMs.value = null; runId.value = ''; error.value = ''; selected.value = 'data'
}
watch(() => [props.companyId, props.scenario], () => { reset(); refreshHistory() }, { immediate: true })
onBeforeUnmount(() => { generation++; controller?.abort() })
</script>

<template>
  <div class="calculation-workflow">
    <div class="calculation-overview">
    <div class="calculation-heading">
      <div><p class="calculation-eyebrow">企业数据到融资建议</p><h2>计算过程工作台</h2><p class="sub">读取后台入库数据，逐步呈现模型计算及决策依据。</p></div>
      <div class="calculation-actions"><button v-if="running" class="review-secondary" @click="controller?.abort()">停止接收</button><button class="review-primary" :disabled="running" @click="run">{{ running ? '后台正在计算…' : runId ? '重新运行分析' : '运行完整分析' }}</button></div>
    </div>
    <div class="calculation-context"><span>{{ analysis.company.company_name }}</span><span>{{ scenario }}</span><span>数据 V{{ dataVersion?.version ?? analysis.data_version.version }} · {{ dataVersion?.period ?? analysis.data_version.period }}</span><span>{{ running ? `已完成 ${doneCount} / ${definitions.length} 个阶段` : totalMs != null ? `已完成 · ${duration(totalMs)}` : '等待运行' }}</span></div>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p>
    <p v-if="stale" class="review-error" role="status">后台数据已更新，本次结果保留原计算版本，请重新运行以获取最新结果。</p>

    <ol class="calculation-stages" aria-label="实际计算阶段">
      <li v-for="(step, index) in definitions" :key="step.id" :class="[states[step.id]?.status || 'pending', { selected: selected === step.id }]">
        <button @click="selected=step.id" :aria-current="selected===step.id ? 'step' : undefined"><span class="calculation-stage-number">{{ states[step.id]?.status === 'completed' ? '✓' : String(index + 1).padStart(2, '0') }}</span><b>{{ step.name }}</b><small>{{ statusLabel(states[step.id]?.status) }}</small></button>
      </li>
    </ol>
    </div>

    <div class="calculation-body">
      <section class="calculation-detail" :aria-busy="stepState.status==='running'">
        <div class="calculation-detail-heading"><div><span>{{ active.method }}</span><h3>{{ active.name }}</h3></div><span class="calculation-duration">{{ statusLabel(stepState.status) }}<template v-if="stepState.duration_ms != null"> · {{ duration(stepState.duration_ms) }}</template></span></div>
        <p class="calculation-description">{{ active.description }}</p>
        <div v-if="!result" class="calculation-empty"><span v-if="stepState.status==='running'" class="calculation-spinner" aria-hidden="true"></span><b>{{ stepState.status==='running' ? '正在等待本阶段的后端计算结果' : stepState.status==='failed' ? '本阶段未完成，请查看运行记录' : '运行后展示本阶段输入、计算与输出' }}</b><p>阶段结果返回后，图表和数值自动更新。</p></div>

        <div v-else :key="`${runId}-${selected}`" class="calculation-result">
          <template v-if="selected==='data'">
            <div class="calculation-numbers"><div><span>企业能耗记录</span><b>{{ result.energy_records }}<small>条</small></b></div><div><span>报告期间</span><b>{{ result.periods }}<small>期</small></b></div><div><span>园区关联记录</span><b>{{ result.network_relations }}<small>条</small></b></div></div>
            <p class="footnote">数据来源：{{ result.data_version.source }} · 入库时间 {{ new Date(result.data_version.created_at).toLocaleString('zh-CN') }}</p>
            <h4>本次读取的部分能耗事实</h4><div class="table-wrap"><table><thead><tr><th>报告期间</th><th>能源</th><th>能耗量</th><th>产量</th><th>排放因子</th></tr></thead><tbody><tr v-for="row in result.energy_preview" :key="`${row.period}-${row.energy_type}`"><td>{{ row.period }}</td><td>{{ energyName(row.energy_type) }}</td><td>{{ number(row.energy) }}</td><td>{{ number(row.output) }}</td><td>{{ number(row.emission_factor) }}</td></tr></tbody></table></div>
            <div class="calculation-inputs"><span>项目进度 <b>{{ pct(result.input_metrics.project_progress) }}</b></span><span>资金用途一致率 <b>{{ pct(result.input_metrics.fund_usage_match) }}</b></span><span>自有资金到位率 <b>{{ pct(result.input_metrics.own_fund_arrival) }}</b></span><span>数据完整度 <b>{{ pct(result.input_metrics.data_completeness) }}</b></span></div>
          </template>
          <EmissionAttribution v-else-if="selected==='lmdi'" :result="result" />
          <template v-else-if="selected==='transition'">
            <div class="calculation-numbers"><div><span>未来 12 个月达标概率</span><b>{{ pct(result.p_target) }}</b></div><div><span>数据质量</span><b>{{ pct(result.data_quality) }}</b></div><div><span>组合异常分数</span><b>{{ pct(result.anomaly_score) }}</b></div></div>
            <PredictionFactors :explanation="result.explanation" /><p class="footnote">异常分数用于提示人工核验，不直接认定漂绿。验证集 AUC {{ result.model_auc.toFixed(3) }}。</p>
          </template>
          <template v-else-if="selected==='network'">
            <div class="calculation-numbers"><div><span>企业自身风险</span><b>{{ pct(result.own_risk) }}</b></div><div><span>园区综合风险</span><b>{{ pct(result.network_risk) }}</b></div><div><span>参与计算的关联记录</span><b>{{ result.relation_count }}</b></div></div>
            <div class="calculation-risk-rows"><div v-for="item in [{label:'一阶净影响',value:result.first_order_risk},{label:'二阶净影响',value:result.second_order_risk}]" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value >= 0 ? '+' : '' }}{{ (item.value*100).toFixed(2) }} 个百分点</b></div></div>
            <h4>主要风险传播路径</h4><ol class="calculation-paths"><li v-for="(path,index) in result.paths" :key="index"><span>{{ path.path }}</span><b>{{ pct(path.contribution) }}</b></li></ol><p v-if="!result.paths.length" class="footnote">当前没有显著传播路径。</p>
          </template>
          <template v-else-if="selected==='finance'">
            <FinancingEquation :decision="result" /><div class="calculation-numbers"><div><span>建议利率</span><b>{{ pct(result.suggested_rate) }}</b></div><div><span>RAROC</span><b>{{ pct(result.raroc) }}</b></div><div><span>收益底线 {{ pct(result.raroc_threshold) }}</span><b :class="{'calculation-failed-text':!result.raroc_passed}">{{ result.raroc_passed ? '校验通过' : '需调整方案' }}</b></div></div><p class="calculation-conclusion">{{ result.action }}。融资结果为辅助建议，须经银行人工审批。</p>
          </template>
          <template v-else-if="selected==='stress'">
            <p class="footnote">{{ result.normal_scenario }}与{{ result.stress_scenario }}分别计算；压力情景是假设冲击。</p><div class="table-wrap"><table><thead><tr><th>指标</th><th>正常情景</th><th>燃气压力情景</th></tr></thead><tbody><tr><td>达标概率</td><td>{{ pct(result.normal.p_target) }}</td><td>{{ pct(result.stress.p_target) }}</td></tr><tr><td>园区综合风险</td><td>{{ pct(result.normal.network_risk) }}</td><td>{{ pct(result.stress.network_risk) }}</td></tr><tr><td>建议融资额度</td><td>{{ amount(result.normal.final_limit) }}</td><td>{{ amount(result.stress.final_limit) }}</td></tr><tr><td>RAROC</td><td>{{ pct(result.normal.raroc) }}</td><td>{{ pct(result.stress.raroc) }}</td></tr></tbody></table></div>
          </template>
          <template v-else-if="selected==='review'">
            <div class="calculation-numbers"><div><span>当前版本核验任务</span><b>{{ result.task_count }}<small>项</small></b></div><div><span>数据版本</span><b>V{{ result.data_version.version }}</b></div><div><span>审批方式</span><b>人工审批</b></div></div><ul class="calculation-tasks"><li v-for="task in result.tasks" :key="task.id"><span>{{ task.title }}</span><b>{{ taskStatus(task.status) }}</b></li></ul><p v-if="!result.tasks.length" class="footnote">当前数据版本未生成核验任务。</p><p class="footnote">任务依据实际入库数据生成，不将压力测试中的假设变化当作企业已发生事实。</p>
          </template>
        </div>
      </section>

      <section class="calculation-log" aria-label="后端运行记录"><h3>本次运行记录</h3><p v-if="runId" class="calculation-run-id">{{ runId }}</p><p v-else class="footnote">运行后显示实际阶段状态与时间。</p><ol><li v-for="event in logs.filter(item=>item.type!=='started')" :key="event.sequence" :class="event.status || event.type"><time>{{ new Date(event.at).toLocaleTimeString('zh-CN', {hour12:false}) }}</time><span>{{ event.type==='completed' ? '全部完成，结果已留痕' : event.type==='error' ? event.message : `${definitions.find(step=>step.id===event.stage)?.name} · ${statusLabel(event.status)}` }}</span><small v-if="event.duration_ms != null">{{ duration(event.duration_ms) }}</small></li></ol></section>
    </div>
    <div class="calculation-history" v-if="history.length"><h3>最近运行</h3><div v-for="record in history" :key="record.workflow_id"><span>{{ new Date(record.created_at).toLocaleString('zh-CN') }}</span><b>{{ statusLabel(record.status) }}</b><span>{{ record.scenario }}</span><span v-if="record.data_version">数据 V{{ record.data_version.version }}</span><small>{{ record.workflow_id }}</small></div></div>
  </div>
</template>
