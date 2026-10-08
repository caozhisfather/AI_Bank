<script setup>
defineProps({ items: Array, valueKey: String, labelKey: String, signed: Boolean, formatter: Function })
</script>
<template>
  <div class="bar-list">
    <div v-for="item in items" :key="item[labelKey]" class="bar-row">
      <span>{{ item[labelKey] }}</span>
      <div class="bar-track"><i :class="{ negative: item[valueKey] < 0 }" :style="{ width: `${Math.min(100, Math.abs(item[valueKey]) * (signed ? 80 : 100))}%` }"></i></div>
      <b>{{ formatter ? formatter(item[valueKey]) : item[valueKey] }}</b>
    </div>
  </div>
</template>
