<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ explanation: { type: Object, default: null } })
const expanded = ref(false)
const allFactors = computed(() => [...(props.explanation?.items || [])]
  .filter(item => Number.isFinite(item.contribution_pp))
  .sort((a, b) => Math.abs(b.contribution_pp) - Math.abs(a.contribution_pp)))
const factors = computed(() => expanded.value ? allFactors.value : allFactors.value.slice(0, 5))
const remaining = computed(() => allFactors.value.slice(5).reduce((sum, item) => sum + item.contribution_pp, 0))
const scale = computed(() => Math.max(0, ...allFactors.value.map(item => Math.abs(item.contribution_pp))) || 1)
const pp = value => `${value >= .005 ? '+' : ''}${(Math.abs(value) < .005 ? 0 : value).toFixed(2)}`
const barStyle = value => {
  const width = Math.abs(value) / scale.value * 50
  return { width: `${width}%`, left: `${value < 0 ? 50 - width : 50}%` }
}
const impactText = value => `${value < 0 ? '降低' : '提高'}达标概率 ${Math.abs(value).toFixed(2)} 个百分点`
watch(() => props.explanation, () => { expanded.value = false })
</script>

<template>
  <div class="prediction-factors">
    <h3>关键因素及其贡献</h3>
    <template v-if="factors.length">
      <p class="prediction-explanation-note" title="贡献相对模型在背景样本上的平均预测概率计算。">正值提高、负值降低达标概率，单位为百分点。</p>
      <ol class="prediction-factor-list" aria-label="SHAP 概率贡献，按影响程度排序">
        <li v-for="(item,index) in factors" :key="item.feature">
          <span class="prediction-factor-rank">{{ String(index + 1).padStart(2,'0') }}</span>
          <div class="prediction-factor-name"><b>{{ item.label }}</b></div>
          <div class="prediction-contribution-track" aria-hidden="true"><i :class="item.contribution_pp < 0 ? 'negative' : 'positive'" :style="barStyle(item.contribution_pp)"></i></div>
          <span class="prediction-factor-amount" :class="item.contribution_pp < 0 ? 'negative' : 'positive'" :aria-label="impactText(item.contribution_pp)">{{ pp(item.contribution_pp) }}<small>个百分点</small></span>
        </li>
      </ol>
      <div v-if="allFactors.length > 5" class="prediction-factor-expansion"><span v-if="!expanded">其余 {{ allFactors.length - 5 }} 项合计 <b>{{ pp(remaining) }} 个百分点</b></span><button @click="expanded=!expanded">{{ expanded ? '收起为关键5项' : `查看全部${allFactors.length}项` }}</button></div>
      <p v-if="Math.abs(explanation.scenario_adjustment_pp) > 1e-8" class="prediction-scenario-note">情景额外调整：{{ pp(explanation.scenario_adjustment_pp) }} 个百分点，独立于上述因素贡献。</p>
    </template>
    <p v-else class="footnote">当前暂无可用的 SHAP 概率贡献。</p>
  </div>
</template>
