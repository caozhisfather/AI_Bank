<script setup>
import { computed } from 'vue'

const props = defineProps({ items: { type: Array, default: () => [] } })
const extent = computed(() => {
  const largest = Math.max(0, ...props.items.map(item => Math.abs(Number(item.value) || 0)))
  if (!largest) return 1
  const step = 10 ** Math.floor(Math.log10(largest)) / 2
  return Math.ceil(largest / step) * step
})
const signed = value => `${value > 0 ? '+' : ''}${value.toFixed(2)}`
const barStyle = value => {
  const width = Math.min(50, Math.abs(value) / extent.value * 50)
  return { width: `${width}%`, left: `${value < 0 ? 50 - width : 50}%` }
}
const meaning = value => value < 0 ? '减排贡献' : value > 0 ? '增排贡献' : '无变化'
</script>

<template>
  <figure class="lmdi-chart" aria-label="LMDI 排放变化贡献图">
    <figcaption>三项效应的排放变化贡献</figcaption>
    <div class="lmdi-legend"><span class="reduction">负值：减排</span><span class="increase">正值：增排</span></div>
    <div class="lmdi-axis"><span>−{{ extent }}</span><span>0</span><span>+{{ extent }}</span></div>
    <div v-for="item in items" :key="item.label" class="lmdi-effect" :aria-label="`${item.label}：${signed(item.value)}，${meaning(item.value)}`">
      <div class="lmdi-effect-label"><span>{{ item.label }}</span><b :class="item.value < 0 ? 'reduction' : item.value > 0 ? 'increase' : ''">{{ signed(item.value) }}</b></div>
      <div class="lmdi-effect-track" aria-hidden="true"><i :class="item.value < 0 ? 'reduction-bar' : 'increase-bar'" :style="barStyle(item.value)"></i></div>
    </div>
    <p>三项共用同一刻度，以 0 为基线；条形长度表示贡献绝对值，非完成进度。</p>
    <small>单位沿用原始能耗与排放因子的核算口径。</small>
  </figure>
</template>
