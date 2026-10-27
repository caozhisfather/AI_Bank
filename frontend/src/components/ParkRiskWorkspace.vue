<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import RiskNetworkGraph from './RiskNetworkGraph.vue'
import RiskComposition from './RiskComposition.vue'
import CreditExposurePanel from './CreditExposurePanel.vue'
import {filterRiskExplanation} from '../utils/networkView'
import {effectLabel} from '../utils/riskDisplay'
const props=defineProps({analysis:{type:Object,required:true},scenario:String,scenarios:Array,scenarioCatalog:Array,updating:Boolean})
const emit=defineEmits(['select','scenario'])
const mode=ref('dependency'),inspected=ref(null),drawer=ref(null)
const filters=ref({order:'all',kind:'all'})
const company=computed(()=>props.analysis.company||{})
const baseline=computed(()=>props.analysis.comparison?.normal||{})
const graph=computed(()=>props.analysis.network_graph||{nodes:[],edges:[]})
const explanation=computed(()=>props.analysis.network_analysis||{incoming_paths:[],outgoing_paths:[],recipients:[]})
const stressed=computed(()=>props.analysis.scenario!=='正常情景')
const scenarioInfo=computed(()=>props.scenarioCatalog?.find(item=>item.name===props.analysis.scenario))
const money=value=>`${Math.round(Number(value||0)).toLocaleString('zh-CN')} 万元`
const pct=value=>`${(Number(value||0)*100).toFixed(2)}%`
const pp=value=>`${value>=0?'+':'−'}${Math.abs(Number(value||0)*100).toFixed(2)}个百分点`
const incoming=computed(()=>explanation.value.incoming_paths||[])
const recipients=computed(()=>explanation.value.recipients||[])
const filtered=computed(()=>filterRiskExplanation(explanation.value,graph.value.edges,filters.value))
const direct=computed(()=>graph.value.edges.filter(edge=>edge.source===company.value.company_id||edge.target===company.value.company_id))
const dependsOn=computed(()=>new Set(direct.value.filter(edge=>edge.target===company.value.company_id).map(edge=>edge.source)).size)
const dependentCount=computed(()=>new Set(direct.value.filter(edge=>edge.source===company.value.company_id).map(edge=>edge.target)).size)
const nodeInfo=computed(()=>inspected.value?.type==='node'?graph.value.nodes.find(node=>node.company_id===inspected.value.id):null)
const edgeInfo=computed(()=>inspected.value?.type==='edge'?graph.value.edges.find(edge=>edge.relation_id===inspected.value.id):null)
const pathInfo=computed(()=>inspected.value?.type==='path'?incoming.value[inspected.value.index]:null)
const recipientInfo=computed(()=>inspected.value?.type==='recipient'?filtered.value.recipients.find(node=>node.company_id===inspected.value.id):null)
const selectedOutgoing=computed(()=>nodeInfo.value?recipients.value.find(item=>item.company_id===nodeInfo.value.company_id):null)
const close=()=>{inspected.value=null}
watch(inspected,async item=>{await nextTick();if(item&&!drawer.value.open)drawer.value.showModal();else if(!item&&drawer.value?.open)drawer.value.close()})
watch(()=>company.value.company_id,close)
watch(mode,close)
function changeScenario(event){close();emit('scenario',event.target.value)}
function analyzeNode(){const id=nodeInfo.value?.company_id;if(id){close();emit('select',id)}}
const riskRows=[['own_risk','自身风险'],['first_order_risk','一阶园区净影响'],['second_order_risk','二阶园区净影响'],['network_risk','综合风险']]
</script>
<template>
  <div class="park-risk-heading"><div><h2>园区风险分析</h2><p class="sub">{{company.company_name}} · {{analysis.scenario}}</p></div><label><span>分析情景</span><select :value="scenario" :disabled="updating" @change="changeScenario"><option v-for="item in scenarios" :key="item" :value="item">{{item}}</option></select></label></div>
  <div class="park-view-tabs" aria-label="图谱视图"><button :class="{active:mode==='dependency'}" :aria-pressed="mode==='dependency'" @click="mode='dependency'">业务依赖关系</button><button :class="{active:mode==='risk'}" :aria-pressed="mode==='risk'" @click="mode='risk'">风险传导</button><span v-if="updating" role="status">计算中…</span><span v-else-if="stressed">与正常情景对比 · {{scenarioInfo?.driver}}</span></div>
  <div v-if="stressed" class="park-stress-summary" aria-label="压力情景对比">
    <div><span>当前企业综合风险</span><p>{{pct(baseline.network_risk)}} <i>→</i> <b>{{pct(company.network_risk)}}</b></p><strong>{{pp(company.network_risk-baseline.network_risk)}}</strong></div>
    <div v-if="company.evaluation_model!=='operating'"><span>建议融资额度</span><p>{{money(baseline.final_limit)}} <i>→</i> <b>{{money(company.final_limit)}}</b></p><strong>{{company.final_limit-baseline.final_limit>=0?'+':'−'}}{{money(Math.abs(company.final_limit-baseline.final_limit))}}</strong></div>
    <div><span>预警等级</span><p>{{baseline.warning_level}} <i>→</i> <b>{{company.warning_level}}</b></p><small>图中展示所选情景下的风险</small></div>
  </div>
  <RiskNetworkGraph :graph="graph" :explanation="explanation" :selected-company-id="company.company_id" :mode="mode" :stressed="stressed" :scenario="analysis.scenario" :aria-busy="updating" @inspect="inspected=$event" @filter="filters=$event" @select="!updating&&emit('select',$event)" />
  <template v-if="mode==='dependency'">
    <div class="dependency-summary"><div><span>直接依赖的主体</span><b>{{dependsOn}} 家</b></div><div><span>直接依赖本企业的主体</span><b>{{dependentCount}} 家</b></div><div><span>直接依赖关系</span><b>{{direct.length}} 条</b></div></div>
    <details class="dependency-detail"><summary>当前企业依赖关系明细</summary><div class="table-wrap"><table><thead><tr><th>依赖关系</th><th>类型</th><th>强度</th><th></th></tr></thead><tbody><tr v-for="edge in direct" :key="edge.relation_id"><td>{{edge.target_name}} → {{edge.source_name}}</td><td>{{edge.relation_type}}</td><td>{{pct(edge.weight)}}</td><td><button class="park-text-button" @click="inspected={type:'edge',id:edge.relation_id}">查看依据</button></td></tr><tr v-if="!direct.length"><td colspan="4">暂无已明确方向的直接依赖关系。</td></tr></tbody></table></div></details>
  </template>
  <template v-else>
    <RiskComposition :company="company" />
    <div class="park-risk-lists">
      <section aria-label="主要传入影响"><h3>主要传入影响</h3><div v-for="(path,index) in filtered.incoming.slice(0,3)" :key="path.path" class="park-path-row"><button @click="inspected={type:'path',index:path.index}"><small>0{{index+1}} · {{effectLabel(path.contribution,path.order)}}</small><b>{{path.path}}</b></button><span :class="path.contribution<0?'risk-relief':'risk-increase'">{{pp(path.contribution)}}<small v-if="stressed">较正常 {{pp(path.delta)}}</small></span></div><p v-if="!filtered.incoming.length" class="park-empty">当前筛选暂无传入影响路径。</p></section>
      <section aria-label="主要受影响主体"><h3>主要受影响主体</h3><div v-for="(item,index) in filtered.recipients.slice(0,3)" :key="item.company_id" class="park-path-row"><button @click="inspected={type:'recipient',id:item.company_id}"><small>0{{index+1}} · {{item.contribution<0?'本企业缓释贡献':'本企业风险传出'}}</small><b>{{item.company_name}}</b></button><span :class="item.contribution<0?'risk-relief':'risk-increase'">{{pp(item.contribution)}}<small v-if="stressed">较正常 {{pp(item.delta)}}</small></span></div><p v-if="!filtered.recipients.length" class="park-empty">当前筛选暂无对外影响主体。</p></section>
    </div>
    <h3 class="park-exposure-title">对外影响授信覆盖</h3><CreditExposurePanel :exposure="analysis.affected_credit_exposure" @select="emit('select',$event)" />
  </template>
  <dialog ref="drawer" class="park-risk-drawer" aria-label="风险与依赖详情" @cancel.prevent="close" @click="event=>{if(event.target===drawer)close()}">
    <div class="park-drawer-head"><div><small>{{analysis.scenario}}</small><h2>{{nodeInfo?.company_name||recipientInfo?.company_name||(edgeInfo?'依赖关系与风险贡献':'传播路径详情')}}</h2></div><button aria-label="关闭详情" @click="close">×</button></div>
    <div class="park-drawer-body">
      <template v-if="nodeInfo">
        <p class="park-detail-lead">{{nodeInfo.industry}} · {{nodeInfo.in_park===false?'园外关联主体':'园内主体'}} · {{nodeInfo.product}}</p>
        <table><thead><tr><th>风险分量</th><th>正常情景</th><th>当前情景</th><th>变化</th></tr></thead><tbody><tr v-for="[key,label] in riskRows" :key="key"><td>{{label}}</td><td>{{pct(nodeInfo[`baseline_${key}`])}}</td><td>{{pct(nodeInfo[key])}}</td><td>{{pp(nodeInfo[key]-nodeInfo[`baseline_${key}`])}}</td></tr></tbody></table>
        <div v-if="nodeInfo.final_limit!==null&&nodeInfo.final_limit!==undefined" class="park-detail-fact"><span>建议融资额度</span><b>{{money(nodeInfo.baseline_final_limit)}} → {{money(nodeInfo.final_limit)}}</b><span>预警等级</span><b>{{nodeInfo.baseline_warning_level}} → {{nodeInfo.warning_level}}</b></div>
        <div v-if="selectedOutgoing" class="park-detail-fact"><span>当前分析企业对该主体的净影响</span><b>{{pp(selectedOutgoing.contribution)}} <small v-if="stressed">{{pp(selectedOutgoing.delta)}}</small></b></div>
        <button v-if="(nodeInfo.can_analyze||nodeInfo.node_type==='enterprise')&&nodeInfo.company_id!==company.company_id" class="park-primary-button" :disabled="updating" @click="analyzeNode">设为分析企业</button>
      </template>
      <template v-else-if="edgeInfo">
        <p class="park-detail-lead">{{edgeInfo.target_name}} → {{edgeInfo.source_name}}</p><p>{{edgeInfo.dependency_description}}</p>
        <dl class="park-detail-fields"><div v-if="edgeInfo.commodity"><dt>依赖商品或服务</dt><dd>{{edgeInfo.commodity}}</dd></div><div v-if="edgeInfo.share_basis"><dt>份额口径</dt><dd>{{edgeInfo.share_basis}} · {{pct(edgeInfo.share)}}</dd></div><div v-if="edgeInfo.replacement_days!==null"><dt>替代周期</dt><dd>{{edgeInfo.replacement_days}} 天</dd></div><div><dt>依赖类型</dt><dd>{{edgeInfo.relation_type}}</dd></div><div><dt>依赖强度</dt><dd>{{pct(edgeInfo.weight)}}</dd></div><div><dt>风险传导方向</dt><dd>{{edgeInfo.source_name}} → {{edgeInfo.target_name}}</dd></div><div><dt>数据来源</dt><dd>{{edgeInfo.data_source}}</dd></div><div><dt>报告期</dt><dd>{{edgeInfo.reporting_period}}</dd></div><div><dt>核验状态</dt><dd>{{edgeInfo.evidence_status}} · {{edgeInfo.direction_basis}}</dd></div></dl>
        <table><thead><tr><th>一阶净影响</th><th>正常情景</th><th>当前情景</th><th>变化</th></tr></thead><tbody><tr><td>{{edgeInfo.source_name}} → {{edgeInfo.target_name}}</td><td>{{pp(edgeInfo.baseline_direct_contribution)}}</td><td>{{pp(edgeInfo.direct_contribution)}}</td><td>{{pp(edgeInfo.contribution_delta)}}</td></tr></tbody></table>
        <div class="park-detail-fact"><span>当前风险传入</span><b>{{pp(edgeInfo.gross_contribution)}}</b><span>当前缓释贡献</span><b class="risk-relief">{{pp(-edgeInfo.mitigation_contribution)}}</b></div>
        <dl v-if="edgeInfo.mitigation_capacity>0" class="park-detail-fields"><div><dt>缓释机制</dt><dd>{{edgeInfo.mitigation_mechanism}}</dd></div><div><dt>当前有效缓释系数</dt><dd>{{pct(edgeInfo.mitigation_capacity)}}</dd></div><div><dt>缓释参数来源</dt><dd>{{edgeInfo.mitigation_source}} · {{edgeInfo.mitigation_period}}</dd></div><div><dt>参数状态</dt><dd>{{edgeInfo.mitigation_status}}</dd></div></dl>
      </template>
      <template v-else-if="pathInfo">
        <p class="park-detail-lead">{{pathInfo.path}}</p><div class="park-detail-fact"><span>传播层级</span><b>{{pathInfo.order}} 阶</b><span>正常情景净影响</span><b>{{pp(pathInfo.baseline_contribution)}}</b><span>当前风险传入</span><b>{{pp(pathInfo.gross_contribution)}}</b><span>当前缓释贡献</span><b class="risk-relief">{{pp(-pathInfo.mitigation_contribution)}}</b><span>当前情景净影响</span><b>{{pp(pathInfo.contribution)}}</b><span>净影响变化</span><b>{{pp(pathInfo.delta)}}</b></div>
      </template>
      <template v-else-if="recipientInfo">
        <div class="park-detail-fact"><span>该主体综合风险</span><b>{{pct(recipientInfo.baseline_risk)}} → {{pct(recipientInfo.risk)}}</b><span>该主体总风险变化</span><b>{{pp(recipientInfo.risk_delta)}}</b><span>当前分析企业净影响</span><b>{{pp(recipientInfo.baseline_contribution)}} → {{pp(recipientInfo.contribution)}}</b><span>当前风险传出</span><b>{{pp(recipientInfo.gross_contribution)}}</b><span>当前缓释贡献</span><b>{{pp(-recipientInfo.mitigation_contribution)}}</b><span>本企业贡献变化</span><b>{{pp(recipientInfo.delta)}}</b></div>
        <h3>传播路径</h3><div v-for="path in recipientInfo.paths" :key="path.path" class="park-detail-path"><b>{{path.path}}</b><span>{{pp(path.contribution)}} <small v-if="stressed">{{pp(path.delta)}}</small></span></div>
      </template>
      <p v-if="pathInfo||recipientInfo" class="park-detail-note">传播贡献为综合风险截断前的分量；主体总风险变化还可能包含自身冲击与其他来源。</p>
    </div>
  </dialog>
</template>
