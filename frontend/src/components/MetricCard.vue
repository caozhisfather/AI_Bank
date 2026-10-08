<script setup>
defineProps({ label: String, value: String, delta: String, danger: Boolean })
</script>
<template>
  <article class="metric-card">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <small v-if="delta" :class="{ danger }">{{ delta }}</small>
  </article>
</template>
