<script setup>
import { onMounted, ref } from 'vue'
import { getDataStatus } from '../api'
import ReviewWorkspace from './ReviewWorkspace.vue'

defineProps({ user: Object, companyId: String, versionId: Number })
const emit = defineEmits(['changed'])
const snapshot = ref(null), error = ref('')
async function refresh() { snapshot.value = await getDataStatus() }
async function changed() { await refresh(); emit('changed') }
onMounted(async () => { try { await refresh() } catch (e) { error.value = e.message } })
</script>

<template>
  <div class="enterprise-data">
    <h2>数据状态与补充材料</h2><p class="sub">业务数据由后台校验入库。此处查看当前数据版本，并对核验任务补充说明与证明材料。</p>
    <div v-if="snapshot" class="review-stats"><div><span>当前数据版本</span><b>V{{ snapshot.version }}</b></div><div><span>报告期间</span><b>{{ snapshot.period }}</b></div><div><span>能耗记录</span><b>{{ snapshot.record_count }} 条</b></div></div>
    <p v-if="snapshot" class="footnote">最近来源：{{ snapshot.source }} · {{ new Date(snapshot.created_at).toLocaleString('zh-CN') }}</p>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p>
    <div class="enterprise-material-section"><ReviewWorkspace :user="user" :company-id="companyId" :version-id="versionId" :snapshot="snapshot" @changed="changed" /></div>
  </div>
</template>
