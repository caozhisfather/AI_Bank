<script setup>
import { computed } from 'vue'

const props = defineProps({ exposure: { type: Object, default: null } })
defineEmits(['select'])
const ready = computed(() => Number.isFinite(props.exposure?.total_exposure))
const orderLabels = ['当前企业自身', '一阶直接受影响', '二阶间接受影响']
const money = value => Number.isFinite(value) ? `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万元` : '—'
const percent = value => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
</script>

<template>
  <section class="exposure-panel" aria-label="受影响授信敞口">
    <div class="exposure-summary">
      <div class="exposure-total"><span>受影响授信敞口</span><strong>{{ money(exposure?.total_exposure) }}</strong><small>基础授信额度口径</small></div>
      <div><span>覆盖企业</span><strong>{{ ready ? `${exposure.company_count} 家` : '—' }}</strong><small>包含当前企业自身</small></div>
      <div><span>占园区授信比例</span><strong>{{ percent(exposure?.exposure_share) }}</strong><small>园区基础授信 {{ money(exposure?.park_total_exposure) }}</small></div>
    </div>
    <details v-if="ready" class="exposure-details">
      <summary>查看敞口构成与企业明细</summary>
      <div class="exposure-breakdown"><div><span>当前企业自身</span><b>{{ money(exposure.own_exposure) }}</b></div><div><span>一阶直接受影响</span><b>{{ money(exposure.first_order_exposure) }}</b></div><div><span>二阶间接受影响</span><b>{{ money(exposure.second_order_exposure) }}</b></div></div>
      <div class="table-wrap"><table><thead><tr><th>企业</th><th>行业</th><th>传播层级</th><th>基础授信额度</th></tr></thead><tbody><tr v-for="item in exposure.companies" :key="item.company_id"><td><button class="exposure-company" @click="$emit('select', item.company_id)">{{ item.company_name }}</button></td><td>{{ item.industry }}</td><td>{{ orderLabels[item.propagation_order] }}</td><td>{{ money(item.base_limit) }}</td></tr></tbody></table></div>
    </details>
  </section>
</template>
