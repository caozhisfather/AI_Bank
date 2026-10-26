<script setup>
import { computed } from 'vue'
import { isProductionLed } from '../utils/assessmentState'

const props = defineProps({ result: { type: Object, required: true } })
const productionLed = computed(() => isProductionLed(props.result))
const signed = value => `${value > 0 ? '+' : ''}${(Math.abs(value) < .005 ? 0 : value).toFixed(2)}%`
const percentages = computed(() => props.result.effect_percentages || Object.fromEntries(
  ['activity', 'efficiency', 'energy_structure', 'process'].map(key => [key,
    Number.isFinite(props.result[key]) && props.result.base_emissions > 0 ? props.result[key] / props.result.base_emissions * 100 : null])
))
const netChange = computed(() => props.result.total_change_percentage ?? props.result.total_change / props.result.base_emissions * 100)
const steps = computed(() => {
  let level = 0
  return [['activity', '产量效应'], ['efficiency', '能效效应'], ['energy_structure', '能源结构效应'], ['process', '工艺效应']].map(([key, label]) => {
    const value = percentages.value[key]
    const item = { label, start: level, end: level + (value ?? 0), value, missing: !Number.isFinite(value) }
    level = item.end
    return item
  })
})
const axisStep = computed(() => {
  const extent = Math.max(0, ...steps.value.flatMap(item => [Math.abs(item.start), Math.abs(item.end)]))
  return extent ? 10 ** Math.floor(Math.log10(extent)) : 1
})
const ceiling = computed(() => Math.max(axisStep.value, Math.ceil(Math.max(0, ...steps.value.map(item => item.end)) / axisStep.value) * axisStep.value))
const floor = computed(() => Math.floor(Math.min(0, ...steps.value.map(item => item.end)) / axisStep.value) * axisStep.value)
const ticks = computed(() => Array.from({ length: Math.round((ceiling.value - floor.value) / axisStep.value) + 1 }, (_, index) => floor.value + index * axisStep.value))
const axisLabel = value => `${value.toFixed(Math.max(0, Math.min(4, -Math.floor(Math.log10(axisStep.value)))))}%`
const y = value => 232 - (value - floor.value) / (ceiling.value - floor.value) * 196
const x = index => 110 + index * 170
const color = item => item.value < 0 ? '#009665' : '#e34444'
const chartDescription = computed(() => steps.value.map(item => `${item.label}：${item.missing ? '待补充' : signed(item.value)}`).join('；'))
</script>

<template>
  <div class="emission-attribution">
    <div class="attribution-context"><span>{{ result.base_period }} <i>→</i> {{ result.current_period }}</span><span>{{ result.scope }}<em v-if="!result.process_available">工艺数据待补充</em></span></div>
    <div class="attribution-body">
    <div class="attribution-summary">
      <div class="attribution-net-change" title="变化量 ÷ 基期排放量 × 100%"><span>排放净变化</span><b :class="netChange < 0 ? 'reduction' : netChange > 0 ? 'increase' : ''">{{ signed(netChange) }}</b></div>
      <p class="attribution-baseline">较基期（{{ result.base_period }}）</p>
      <p class="attribution-change-direction" :class="netChange < 0 ? 'reduction' : netChange > 0 ? 'increase' : ''"><span aria-hidden="true">{{ netChange < 0 ? '↓' : netChange > 0 ? '↑' : '→' }}</span> {{ Math.abs(netChange).toFixed(2) }} 个百分点</p>
    </div>
    <figure class="attribution-waterfall" aria-label="四因素减排归因百分比瀑布图">
      <div class="attribution-chart-meta" title="各项均以同一基期排放量为分母；按原值计算，显示值四舍五入。"><div><span><i class="reduction-key"></i>负值：减排</span><span><i class="increase-key"></i>正值：增排</span></div></div>
      <div class="attribution-chart-scroll"><svg viewBox="0 0 800 292" role="img" :aria-label="chartDescription">
        <g v-for="tick in ticks" :key="tick"><line x1="70" x2="778" :y1="y(tick)" :y2="y(tick)" stroke="#e4ebe6" /><text x="61" :y="y(tick) + 4" text-anchor="end" class="waterfall-tick">{{ axisLabel(tick) }}</text></g>
        <line x1="70" x2="778" :y1="y(0)" :y2="y(0)" stroke="#91a69a" />
        <g v-for="(item,index) in steps" :key="item.label">
          <line v-if="index < steps.length - 1" :x1="x(index) + 72" :x2="x(index + 1)" :y1="y(item.end)" :y2="y(item.end)" stroke="#a7b7ac" stroke-dasharray="4 4" />
          <rect v-if="!item.missing" :x="x(index)" :y="Math.min(y(item.start), y(item.end))" width="72" :height="Math.max(2, Math.abs(y(item.start) - y(item.end)))" :fill="color(item)" rx="2" />
          <rect v-else :x="x(index)" :y="y(item.start) - 11" width="72" height="22" fill="#f6f8f7" stroke="#aebbb3" stroke-dasharray="4 3" rx="2" />
          <text :x="x(index) + 36" :y="Math.min(y(item.start), y(item.end)) - (item.missing ? 20 : 9)" text-anchor="middle" :fill="item.missing ? '#829088' : color(item)" class="waterfall-value">{{ item.missing ? '待补充' : signed(item.value) }}</text>
          <text :x="x(index) + 36" y="262" text-anchor="middle" class="waterfall-label">{{ item.label }}</text>
        </g>
      </svg></div>
    </figure>
    </div>
    <div class="attribution-conclusion" :class="{'attribution-production-warning':productionLed}"><span class="attribution-conclusion-icon" aria-hidden="true"><svg v-if="productionLed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 6v8m0 4h.01" /></svg><svg v-else viewBox="0 0 24 24"><path d="M19 4C10 3 5 8 5 14c0 3 2 5 5 6 0-6 3-10 8-13-4 4-6 8-7 13 7-2 10-9 8-16Z" fill="currentColor" /></svg></span><p>{{ result.conclusion }}</p></div>
  </div>
</template>
