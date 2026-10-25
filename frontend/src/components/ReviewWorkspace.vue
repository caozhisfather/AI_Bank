<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getMaterial, getReviewTask, getReviewTasks, reviewDecision, submitEvidence } from '../api'

const props = defineProps({ user: Object, companyId: String, versionId: Number, snapshot: Object })
const emit = defineEmits(['changed'])
const isBank = computed(() => props.user?.role === '银行端')
const tasks = ref([]), filter = ref('active'), task = ref(null), busy = ref(false), error = ref(''), message = ref('')
const dialog = ref(null), explanation = ref(''), files = ref([]), correctionEnabled = ref(false), correctionField = ref('project_progress'), correctionValue = ref(''), energyCorrection = ref([]), routeCorrection = ref('[]')
const decision = ref('approve_reasonable'), comment = ref(''), preview = ref(null), materialBusy = ref(false)
const statuses = { awaiting_material: '待企业补充', pending_review: '待银行审核', returned: '退回补充', resolved: '已核验结案', tracking: '持续跟踪', superseded: '历史版本' }
const actions = { submit: '企业提交材料', approve_reasonable: '核验合理并结案', approve_correction: '更正通过并重算', return: '退回补充', track: '确认异常并持续跟踪' }
const fields = { project_progress: '项目执行进度', milestone_delay_days: '里程碑延迟天数', fund_usage_match: '资金用途一致率', own_fund_arrival: '自有资金到位率', cashflow_coverage: '经营现金流覆盖', energy_cost_ratio: '能源成本占比', data_completeness: '数据完整度' }
const percentFields = new Set(['project_progress', 'fund_usage_match', 'own_fund_arrival', 'energy_cost_ratio', 'data_completeness'])
const time = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
const pct = value => `${(value * 100).toFixed(1)}%`
const shown = computed(() => tasks.value.filter(item => filter.value === 'all' || (filter.value === 'active' ? item.is_current && item.status !== 'resolved' : item.status === filter.value)))
const counts = computed(() => ({ pending: tasks.value.filter(t => t.status === 'pending_review').length, awaiting: tasks.value.filter(t => ['awaiting_material', 'returned'].includes(t.status)).length, resolved: tasks.value.filter(t => t.status === 'resolved').length }))
const canSubmit = computed(() => !isBank.value && task.value?.is_current && ['awaiting_material', 'returned', 'tracking'].includes(task.value?.status))
const lastSubmission = computed(() => task.value?.submissions?.at(-1))
const lastImpact = computed(() => task.value?.history?.findLast(item => item.result?.after)?.result)
let previewRequest = 0

async function load() {
  try { tasks.value = (await getReviewTasks()).items } catch (e) { error.value = e.message }
}
function clearPreview() {
  previewRequest++
  if (preview.value?.url) URL.revokeObjectURL(preview.value.url)
  preview.value = null
}
async function open(item) {
  error.value = ''; message.value = ''; clearPreview()
  try {
    task.value = item ? await getReviewTask(item.id) : { id: '', title: '补充其他说明与证明', company_id: props.companyId, company_name: props.snapshot?.company_name, version_id: props.versionId, version: props.snapshot?.version, period: props.snapshot?.period, status: 'awaiting_material', is_current: 1, revision: 0, details: {}, submissions: [], history: [] }
    explanation.value = ''; files.value = []; correctionEnabled.value = false; correctionValue.value = ''; decision.value = 'approve_reasonable'; comment.value = ''
    energyCorrection.value = JSON.parse(JSON.stringify(props.snapshot?.energy_records || []))
    routeCorrection.value = JSON.stringify(props.snapshot?.route_records || [], null, 2)
    await nextTick()
    if (!dialog.value.open) dialog.value.showModal()
  } catch (e) { error.value = e.message }
}
function close() { if (busy.value) return; dialog.value?.close(); task.value = null; clearPreview() }
async function showMaterial(material) {
  clearPreview(); const requestId = previewRequest; materialBusy.value = true
  try {
    const blob = await getMaterial(material.id)
    const text = material.mime.startsWith('text/') ? await blob.text() : null
    if (requestId !== previewRequest) return
    preview.value = { ...material, text, url: text === null ? URL.createObjectURL(blob) : null }
  } catch (e) { error.value = e.message } finally { materialBusy.value = false }
}
function selectedFiles(event) {
  const selected = Array.from(event.target.files || [])
  if (selected.length > 3 || selected.some(file => file.size > 10 * 1024 * 1024)) { error.value = '最多 3 份，每份不超过 10 MB'; event.target.value = ''; return }
  files.value = selected; error.value = ''
}
async function submit() {
  error.value = ''; busy.value = true
  try {
    const form = new FormData()
    form.append('explanation', explanation.value); form.append('task_id', task.value.id); form.append('revision', task.value.revision); form.append('version_id', task.value.version_id)
    const patch = {}
    if (correctionEnabled.value) {
      if (correctionField.value === 'energy') patch.energy_records = energyCorrection.value
      else if (correctionField.value === 'routes') patch.route_records = JSON.parse(routeCorrection.value)
      else {
        if (correctionValue.value === '' || !Number.isFinite(Number(correctionValue.value))) throw new Error('请填写有效的更正数值')
        patch.features = { [correctionField.value]: Number(correctionValue.value) / (percentFields.has(correctionField.value) ? 100 : 1) }
      }
    }
    form.append('corrections', JSON.stringify(patch))
    files.value.forEach(file => form.append('files', file))
    task.value = await submitEvidence(form); message.value = '材料已提交，等待银行审核。原始数据和评分保持当前状态。'
    await load(); emit('changed')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function decide() {
  error.value = ''; busy.value = true
  try {
    const result = await reviewDecision(task.value.id, { revision: task.value.revision, action: decision.value, comment: comment.value })
    task.value = result.task; message.value = '审核结论已保存，相关指标已重新计算。'; await load(); emit('changed')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
watch(() => props.versionId, async () => {
  try {
    await load()
    if (task.value?.id && !busy.value) task.value = await getReviewTask(task.value.id)
  } catch (e) { error.value = e.message }
})
onMounted(load)
onBeforeUnmount(clearPreview)
</script>

<template>
  <div class="review-workspace">
    <div class="review-toolbar"><div><h2>{{ isBank ? '审核任务清单' : '补充说明与证明材料' }}</h2><p class="sub">按企业、报告期间和数据版本核验，留存材料、结论及处理前后变化</p></div><button v-if="!isBank" class="review-primary" @click="open(null)">补充其他说明</button><button class="review-secondary" @click="load">刷新任务</button></div>
    <div class="review-stats"><div><span>待银行审核</span><b>{{ counts.pending }}</b></div><div><span>待企业补充</span><b>{{ counts.awaiting }}</b></div><div><span>已核验结案</span><b>{{ counts.resolved }}</b></div></div>
    <div class="review-filters" aria-label="审核任务状态筛选"><button v-for="item in [['active','当前待办'],['pending_review','待审核'],['resolved','已结案'],['all','全部与历史']]" :key="item[0]" :class="{active:filter===item[0]}" @click="filter=item[0]">{{ item[1] }}</button></div>
    <p v-if="error && !task" class="review-error" role="alert">{{ error }}</p>
    <div class="table-wrap"><table><thead><tr><th>企业与事项</th><th>期间／版本</th><th>状态</th><th>材料提交</th><th>操作</th></tr></thead><tbody><tr v-for="item in shown" :key="item.id"><td><b>{{ item.company_name }}</b><small class="review-table-sub">{{ item.title }}</small></td><td>{{ item.period }}<small class="review-table-sub">V{{ item.version }}</small></td><td><span class="review-status" :class="item.status">{{ statuses[item.status] }}</span></td><td>{{ item.submission_count }} 次</td><td><button class="review-link" @click="open(item)">{{ isBank ? '查看并审核' : '查看／补充' }}</button></td></tr><tr v-if="!shown.length"><td colspan="5" class="review-empty">当前范围暂无任务。接口数据更新后，系统会重新识别并生成需核验事项。</td></tr></tbody></table></div>
    <p class="footnote">审核针对实际数据版本；压力测试情景单独测算。项目、资金和园区的实际风险继续纳入评价。</p>

    <dialog ref="dialog" class="review-drawer" @cancel.prevent="close">
      <template v-if="task">
        <header class="review-drawer-header"><div><small>{{ task.id || '企业主动补充' }}</small><h2>{{ task.title }}</h2><p>{{ task.company_name }} · {{ task.period }} · V{{ task.version }}</p></div><button class="review-close" aria-label="关闭审核窗口" :disabled="busy" @click="close">×</button></header>
        <div class="review-drawer-body">
          <div class="review-case-meta"><span class="review-status" :class="task.status">{{ statuses[task.status] }}</span><span>{{ task.is_current ? '当前生效数据版本' : '历史版本，仅供追溯' }}</span></div>
          <section class="review-case-section"><h3>异常与核验范围</h3><p>{{ task.details.description || '企业主动补充本期转型相关说明与证明材料。' }}</p><div v-if="task.kind==='energy_spike'" class="review-comparison"><span>上期单位产量排放 <b>{{ task.details.previous_intensity.toFixed(3) }}</b></span><span>本期 <b>{{ task.details.current_intensity.toFixed(3) }}</b></span><span>变化 <b>{{ pct(task.details.value) }}</b></span></div><p v-else-if="task.kind==='data_anomaly'">原始模型异常分数 {{ pct(task.details.value) }}，核验阈值 {{ pct(task.details.threshold) }}。</p><p v-else-if="task.details.value!==undefined">检测值 {{ task.details.value }}，核验阈值 {{ task.details.threshold }}。</p></section>
          <p v-if="error" class="review-error" role="alert">{{ error }}</p><p v-if="message" class="review-success" role="status">{{ message }}</p>
          <section v-for="(submission, index) in task.submissions" :key="submission.id" class="review-case-section"><h3>第 {{ index + 1 }} 次企业说明</h3><p class="review-prewrap">{{ submission.explanation }}</p><small>{{ submission.actor }} · {{ time(submission.created_at) }}</small><div class="review-material-list"><button v-for="material in submission.materials" :key="material.id" @click="showMaterial(material)">{{ material.name }} <small>{{ (material.size/1024).toFixed(1) }} KB · 预览</small></button></div><div v-if="Object.keys(submission.corrections).length" class="review-proposed"><h4>企业提出的数据更正</h4><p v-for="(value,key) in submission.corrections.features" :key="key">{{ fields[key] || key }}：{{ percentFields.has(key) ? pct(value) : value }}</p><div v-if="submission.corrections.energy_records" class="table-wrap"><table><thead><tr><th>能源</th><th>能耗</th><th>产量</th><th>排放因子</th></tr></thead><tbody><tr v-for="row in submission.corrections.energy_records" :key="row.energy_type"><td>{{ row.energy_type }}</td><td>{{ row.energy }}</td><td>{{ row.output }}</td><td>{{ row.emission_factor }}</td></tr></tbody></table></div><div v-if="submission.corrections.route_records" class="table-wrap"><table><thead><tr><th>期间</th><th>工艺路线</th><th>产量</th><th>非燃烧过程排放</th><th>分能源明细</th></tr></thead><tbody><tr v-for="row in submission.corrections.route_records" :key="`${row.period}-${row.route_id}`"><td>{{ row.period }}</td><td>{{ row.route_id }}</td><td>{{ row.output }}</td><td>{{ row.process_emissions }}</td><td><div v-for="energy in row.energy_records" :key="energy.energy_type">{{ energy.energy_type }}：{{ energy.energy }} · 因子 {{ energy.emission_factor }}</div></td></tr></tbody></table></div><small>银行选择“更正通过”后才会形成新数据版本。</small></div></section>
          <section v-if="materialBusy || preview" class="review-case-section review-preview"><h3>证明材料预览</h3><p v-if="materialBusy">正在加载材料…</p><template v-if="preview"><p>{{ preview.name }}</p><pre v-if="preview.text!==null">{{ preview.text }}</pre><img v-else-if="preview.mime.startsWith('image/')" :src="preview.url" :alt="preview.name"><iframe v-else :src="preview.url" :title="preview.name" sandbox="allow-same-origin"></iframe><a v-if="preview.url" :href="preview.url" :download="preview.name">下载原始材料</a></template></section>
          <form v-if="canSubmit" class="review-case-section review-submit" @submit.prevent="submit"><h3>补充本事项说明</h3><label>情况说明<textarea v-model="explanation" required minlength="5" maxlength="6000" rows="4" placeholder="说明异常发生时间、原因、影响范围及证明材料对应关系"></textarea></label><label>证明材料<input type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" multiple @change="selectedFiles"></label><small>PDF／PNG／JPG／UTF-8 TXT，最多 3 份，每份 10 MB。可先提交说明，银行核验通过需有佐证材料。</small><label class="review-checkbox"><input type="checkbox" v-model="correctionEnabled">同时提出数据更正</label><div v-if="correctionEnabled" class="review-correction-form"><label>更正项目<select v-model="correctionField"><option v-for="(label,key) in fields" :value="key" :key="key">{{ label }}{{ percentFields.has(key) ? '（%）' : '' }}</option><option value="energy">本报告期能耗记录</option><option value="routes">工艺路线明细（含历史补充）</option></select></label><label v-if="!['energy', 'routes'].includes(correctionField)">更正后数值<input v-model="correctionValue" type="number" step="any" required></label><label v-else-if="correctionField==='routes'">工艺明细 JSON<textarea v-model="routeCorrection" required rows="10" spellcheck="false" aria-label="工艺明细 JSON"></textarea><small>提交各期间完整的工艺路线、产量、分能源能耗与非燃烧过程排放。历史明细经银行核验后纳入归因分析。</small></label><div v-else><div v-for="row in energyCorrection" :key="row.energy_type" class="energy-edit-row"><b>{{ row.energy_type }}</b><label>能耗<input v-model.number="row.energy" type="number" min="0.000001" step="any" required></label><label>产量<input v-model.number="row.output" type="number" min="0.000001" step="any" required></label><label>排放因子<input v-model.number="row.emission_factor" type="number" min="0.000001" step="any" required></label></div></div></div><button class="review-primary" :disabled="busy">{{ busy ? '提交中…' : '提交银行审核' }}</button></form>
          <form v-if="isBank && task.status==='pending_review' && task.is_current" class="review-case-section review-decision" @submit.prevent="decide"><h3>银行核验结论</h3><label>处理方式<select v-model="decision"><option value="approve_reasonable">核验合理，关闭本事项</option><option value="approve_correction" :disabled="!Object.keys(lastSubmission?.corrections || {}).length">更正通过，生成新版本并重算</option><option value="return">退回企业补充材料</option><option value="track">确认异常，持续跟踪</option></select></label><p class="footnote">合理说明结案保留原始数值。仅“数据组合异常”结案会解除该版本在正常情景下的组合异常质量扣减；能耗波动、项目或资金事项独立处理。</p><label>审核意见<textarea v-model="comment" required minlength="5" maxlength="4000" rows="3" placeholder="记录核验依据、材料一致性、适用范围与后续处理"></textarea></label><button class="review-primary" :disabled="busy">{{ busy ? '保存并重算中…' : '保存审核结论' }}</button></form>
          <section v-if="lastImpact" class="review-case-section"><h3>最近一次处理前后对比</h3><div class="review-impact"><div><span>转型可信指数</span><b>{{ lastImpact.before.credibility.toFixed(1) }} → {{ lastImpact.after.credibility.toFixed(1) }}</b></div><div><span>数据质量</span><b>{{ pct(lastImpact.before.data_quality) }} → {{ pct(lastImpact.after.data_quality) }}</b></div><div><span>数据版本</span><b>V{{ lastImpact.before.data_version }} → V{{ lastImpact.after.data_version }}</b></div><div><span>原始异常分数</span><b>{{ pct(lastImpact.before.raw_anomaly_score) }} → {{ pct(lastImpact.after.raw_anomaly_score) }}</b></div></div><p class="footnote">当前风险状态：{{ lastImpact.after.warning_level }}。建议融资额度 {{ Math.round(lastImpact.after.final_limit).toLocaleString() }} 万元。</p></section>
          <section v-if="task.history?.length" class="review-case-section"><h3>提交与审核记录</h3><ol class="review-history"><li v-for="event in task.history" :key="event.id"><b>{{ actions[event.action] }}</b><small>{{ event.actor }} · {{ time(event.created_at) }}</small><p>{{ event.comment }}</p></li></ol></section>
        </div>
      </template>
    </dialog>
  </div>
</template>
