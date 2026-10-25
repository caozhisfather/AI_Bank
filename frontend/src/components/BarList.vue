<script setup>
import { computed } from 'vue'

const props = defineProps({ items: Array, valueKey: String, labelKey: String, signed: Boolean, formatter: Function })
const scale = computed(() => props.signed
  ? Math.max(0, ...(props.items || []).map(item => Math.abs(item[props.valueKey]))) || 1
  : 1)
</script>
<template>
  <div class="bar-list">
    <div v-for="item in items" :key="item[labelKey]" class="bar-row">
      <span>{{ item[labelKey] }}</span>
      <div class="bar-track"><i :class="{ negative: item[valueKey] < 0 }" :style="{ width: `${Math.min(100, Math.abs(item[valueKey]) / scale * 100)}%` }"></i></div>
      <b>{{ formatter ? formatter(item[valueKey]) : item[valueKey] }}</b>
    </div>
  </div>
</template>
