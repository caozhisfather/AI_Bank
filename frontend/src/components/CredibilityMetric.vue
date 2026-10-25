<script setup>
import { computed } from 'vue'

const props = defineProps({ attribution: { type: Object, default: null } })
defineEmits(['show-evidence'])
const summary = computed(() => props.attribution?.assessment_summary || '暂无归因结论')
</script>

<template>
  <article class="metric-card credibility-metric attribution-metric" :class="{'attribution-caution':attribution?.total_change_percentage>=0}" aria-label="减排归因评价">
    <span>减排归因评价</span>
    <strong :title="attribution?.conclusion">{{ summary }}</strong>
    <button @click="$emit('show-evidence')" :title="attribution?.conclusion" aria-label="查看减排归因分析">查看归因分析 <i aria-hidden="true">→</i></button>
  </article>
</template>
