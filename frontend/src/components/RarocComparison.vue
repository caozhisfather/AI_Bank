<script setup>
import { computed } from 'vue'

const props = defineProps({ decision: { type: Object, required: true } })
const initial = computed(() => props.decision.raroc_before_adjustment)
const threshold = computed(() => props.decision.raroc_threshold)
const ready = computed(() => Number.isFinite(initial.value) && Number.isFinite(threshold.value))
const difference = computed(() => ready.value ? initial.value - threshold.value : null)
const status = computed(() => {
  if (!ready.value) return 'pending'
  if (Math.abs(difference.value) <= 1e-9) return 'equal'
  return difference.value > 0 ? 'above' : 'below'
})
const adjusted = computed(() => ready.value && props.decision.suggested_rate > props.decision.initial_rate + 1e-9)
const messages = {
  above: {
    title: '高于演示门槛',
    text: '当前方案的初始测算 RAROC 高于演示门槛，风险调整后的收益达到项目设定的资本回报要求。可继续结合企业信用、转型证据和园区风险评估融资方案。'
  },
  below: {
    title: '低于演示门槛',
    text: '当前方案的初始测算 RAROC 低于演示门槛，风险收益匹配尚不足。建议优先复核定价、预期损失与运营成本，调整方案并重新测算后提交人工复核。'
  },
  equal: {
    title: '刚好达到演示门槛',
    text: '当前方案的初始测算 RAROC 刚好达到演示门槛，收益缓冲较小。建议持续跟踪损失与成本变化，并结合其他风险指标开展人工复核。'
  },
  pending: { title: '等待测算结果', text: '正在获取当前企业与情景的 RAROC 测算数据。' }
}
const conclusion = computed(() => messages[status.value])
const percent = value => Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '—'
const amount = value => Number.isFinite(value) ? `${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 万元` : '—'
const gap = computed(() => !ready.value ? '—' : `${status.value === 'above' ? '+' : status.value === 'below' ? '−' : ''}${(Math.abs(difference.value) * 100).toFixed(2)}`)
</script>

<template>
  <section class="raroc-comparison" aria-label="RAROC 风险收益校验">
    <header class="raroc-heading"><h3>RAROC 风险收益校验</h3><span>风险调整资本收益率</span></header>
    <div class="raroc-stats">
      <div class="raroc-stat raroc-initial-stat" :class="status">
        <div class="raroc-stat-heading"><span class="raroc-stat-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><path d="m12 12 7-7m-3 0h3v3" /></svg></span><span>初始测算 RAROC</span></div>
        <strong>{{ percent(initial) }}</strong><small>按初始建议利率 {{ percent(decision.initial_rate) }} 计算</small>
      </div>
      <div class="raroc-stat benchmark">
        <div class="raroc-stat-heading"><span class="raroc-stat-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 13h3v7H4zm6-5h3v12h-3zm6-4h3v16h-3zM3 4h7" /></svg></span><span>演示 RAROC 门槛</span></div>
        <strong>{{ percent(threshold) }}</strong><small>项目设定的风险收益基准</small>
      </div>
      <div class="raroc-stat gap-stat" :class="status">
        <div class="raroc-stat-heading"><span class="raroc-stat-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path v-if="status === 'below'" d="m4 6 6 6 4-4 6 9m-5 0h5v-5" /><path v-else-if="status === 'above'" d="m4 17 6-6 4 4 6-9m-5 0h5v5" /><path v-else d="M5 9h14M5 15h14" /></svg></span><span>与门槛差额</span></div>
        <strong>{{ gap }}<em v-if="ready">百分点</em></strong><small>初始测算值 − 演示门槛</small>
      </div>
    </div>
    <div class="raroc-conclusion" :class="status" role="status">
      <span class="raroc-result-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path v-if="status === 'above'" d="m6 12 4 4 8-9" /><path v-else-if="status === 'pending'" d="M12 6v6l4 2" /><path v-else d="M12 6v8m0 4h.01" /></svg></span>
      <div><b>{{ conclusion.title }}</b><p>{{ conclusion.text }}</p></div>
    </div>
    <div v-if="adjusted" class="raroc-adjustment"><b>定价校验后的结果</b><p>建议利率由 {{ percent(decision.initial_rate) }} 调整为 {{ percent(decision.suggested_rate) }}，调整后 RAROC 为 <strong>{{ percent(decision.raroc) }}</strong>。上方对比保留初始测算结果，便于识别方案原有的收益缺口。</p></div>
    <details v-if="ready" class="raroc-calculation">
      <summary>查看计算依据</summary>
      <p>RAROC =（贷款收益 − 预期损失 − 运营成本）÷ 风险资本</p>
      <dl><div><dt>初始贷款收益</dt><dd>{{ amount(decision.loan_income_before_adjustment) }}</dd></div><div><dt>预期损失</dt><dd>{{ amount(decision.expected_loss) }}</dd></div><div><dt>运营成本</dt><dd>{{ amount(decision.operating_cost) }}</dd></div><div><dt>风险资本</dt><dd>{{ amount(decision.risk_capital) }}</dd></div></dl>
    </details>
  </section>
</template>
