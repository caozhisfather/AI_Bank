<script setup>
import { computed } from 'vue'

const props = defineProps({ evidence: { type: Object, default: null } })
const emissionEffect = computed(() => {
  const data = props.evidence?.emissions
  return Number.isFinite(data?.efficiency_effect) && Number.isFinite(data?.energy_structure_effect)
    ? data.efficiency_effect + data.energy_structure_effect : null
})
const percent = value => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
const signed = value => Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}` : '—'
const days = value => Number.isFinite(value) ? `${value} 天` : '—'
</script>

<template>
  <section class="evidence-assessment" aria-label="多维转型证据评估">
    <div class="evidence-heading"><h3>四维转型证据</h3><span>逐项核验转型表现</span></div>
    <div class="evidence-grid">
      <article>
        <h4><i>01</i>减排成效</h4>
        <dl><div><dt>能效及能源结构效应</dt><dd>{{ signed(emissionEffect) }}</dd></div><div><dt>能源相关排放净变化</dt><dd>{{ signed(evidence?.emissions?.net_change) }}</dd></div></dl>
        <p>{{ evidence?.emissions?.base_period || '—' }} → {{ evidence?.emissions?.current_period || '—' }}；负值表示减排，沿用原始数据核算单位。</p>
      </article>
      <article>
        <h4><i>02</i>项目履约</h4>
        <dl><div><dt>项目执行进度</dt><dd>{{ percent(evidence?.project?.progress) }}</dd></div><div><dt>里程碑延迟</dt><dd>{{ days(evidence?.project?.milestone_delay_days) }}</dd></div></dl>
        <p>依据项目执行记录，结合计划进度与里程碑凭证核验。</p>
      </article>
      <article>
        <h4><i>03</i>资金一致</h4>
        <dl><div><dt>资金用途一致率</dt><dd>{{ percent(evidence?.funds?.usage_match) }}</dd></div><div><dt>自有资金到位率</dt><dd>{{ percent(evidence?.funds?.own_fund_arrival) }}</dd></div></dl>
        <p>依据资金记录，结合合同、发票和支付凭证核验。</p>
      </article>
      <article>
        <h4><i>04</i>数据质量</h4>
        <dl><div><dt>数据完整度</dt><dd>{{ percent(evidence?.data?.completeness) }}</dd></div><div><dt>规则质量评估</dt><dd>{{ percent(evidence?.data?.rule_quality) }}</dd></div><div><dt>异常分数</dt><dd>{{ percent(evidence?.data?.anomaly_score) }}</dd></div></dl>
        <p v-if="evidence?.data?.reviewed">当前版本组合异常已核验合理，原始异常分数保留；数据质量按核验结论重算。</p><p v-else>质量值由完整度与异常惩罚计算；异常分数越高，越需核验。</p>
      </article>
    </div>
  </section>
</template>
