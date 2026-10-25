<script setup>
import { onMounted, ref } from 'vue'
import { getDataStatus, syncEnterpriseData } from '../api'
import ReviewWorkspace from './ReviewWorkspace.vue'

defineProps({ user: Object, companyId: String, versionId: Number })
const emit = defineEmits(['changed'])
const snapshot = ref(null), requestText = ref(''), error = ref(''), result = ref(''), busy = ref(false), exampleKind = ref('normal'), showInterface = ref(false)
const nextPeriod = value => { const [year, month] = value.split('-').map(Number); return `${month===12 ? year+1 : year}-${String(month===12 ? 1 : month+1).padStart(2,'0')}` }
async function refresh() { snapshot.value = await getDataStatus() }
function makeExample() {
  const maintenance = exampleKind.value === 'maintenance'
  const energy = JSON.parse(JSON.stringify(snapshot.value.energy_records))
  if (maintenance) energy.forEach(row => { row.output = Number((row.output * .7).toFixed(4)); row.energy = Number((row.energy * 1.1).toFixed(4)) })
  requestText.value = JSON.stringify({ request_id: crypto.randomUUID(), source_system: maintenance ? '本地演示接口·检修期数据' : '本地演示接口·常规同步', reporting_period: nextPeriod(snapshot.value.period), features: snapshot.value.features, energy_records: energy }, null, 2)
  error.value = ''; result.value = ''
}
async function send() {
  error.value = ''; busy.value = true
  try {
    const response = await syncEnterpriseData(JSON.parse(requestText.value))
    await refresh()
    result.value = response.replayed ? `该请求已接收，保持 V${response.version.version}，没有重复入库。` : `已通过企业接口入库为 V${response.version.version}，异常识别与工作台数据已更新。`
    emit('changed')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function changed() { await refresh(); emit('changed') }
onMounted(async () => { try { await refresh(); makeExample() } catch (e) { error.value = e.message } })
</script>

<template>
  <div class="enterprise-data">
    <h2>企业接口接入</h2><p class="sub">生产、能耗、项目及资金指标由企业授权接口提交，经校验后形成数据库版本</p>
    <div v-if="snapshot" class="review-stats"><div><span>当前数据版本</span><b>V{{ snapshot.version }}</b></div><div><span>报告期间</span><b>{{ snapshot.period }}</b></div><div><span>能耗记录</span><b>{{ snapshot.record_count }} 条</b></div></div>
    <p v-if="snapshot" class="footnote">最近来源：{{ snapshot.source }} · {{ new Date(snapshot.created_at).toLocaleString('zh-CN') }}</p>
    <div class="enterprise-interface"><code>POST /api/v1/enterprise/data-sync</code><p>接口按登录企业身份绑定数据归属，新报告期经校验后入库。已入库期间的修订通过补充材料提出，由银行核验后生效。真实企业系统可按此接口对接；下方提供本地请求演示。</p><button class="review-secondary" @click="showInterface=!showInterface">{{ showInterface ? '收起接口演示' : '展开本地接口演示' }}</button></div>
    <div v-if="showInterface && snapshot" class="enterprise-sync"><label>演示场景<select v-model="exampleKind"><option value="normal">常规接口同步</option><option value="maintenance">检修期能耗波动（下一报告期）</option></select></label><button class="review-secondary" @click="makeExample">生成演示请求</button><p class="footnote">可编辑下方请求后发送。检修示例会新增下一期数据，用于演示异常发现、企业补证和银行审核。</p><label>结构化接口请求<textarea v-model="requestText" rows="10" spellcheck="false" aria-label="结构化接口请求"></textarea></label><button class="review-primary" :disabled="busy" @click="send">{{ busy ? '校验并入库中…' : '发送接口数据' }}</button></div>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p><p v-if="result" class="review-success" role="status">{{ result }}</p>
    <div class="enterprise-material-section"><ReviewWorkspace :user="user" :company-id="companyId" :version-id="versionId" :snapshot="snapshot" @changed="changed" /></div>
  </div>
</template>
