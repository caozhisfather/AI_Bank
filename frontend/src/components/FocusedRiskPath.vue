<script setup>
import { computed, useId } from 'vue'
const props=defineProps({path:{type:Object,required:true},paths:{type:Array,required:true},stressed:Boolean,fullscreen:Boolean,scenario:String})
defineEmits(['back','select','inspect','inspect-edge','fullscreen'])
const selectId=`focused-path-${useId()}`
const pct=value=>Number.isFinite(value)?`${(value*100).toFixed(1)}%`:'—'
const impact=value=>Number.isFinite(value)?`${value>=0?'+':'−'}${Math.abs(value*100).toFixed(2)}`:'—'
const money=value=>Number.isFinite(value)?Math.round(value).toLocaleString('zh-CN'):'—'
const level=risk=>risk>=.55?'high':risk>=.35?'medium':'low'
const delta=(current,base)=>Number.isFinite(current)&&Number.isFinite(base)?current-base:null
const pathChange=computed(()=>delta(props.path.contribution,props.path.baseline_contribution))
const strength=step=>{
  const values=step.relations.map(edge=>edge.weight).filter(Number.isFinite)
  if(!values.length)return '—'
  return Math.min(...values)===Math.max(...values)?pct(values[0]):`${pct(Math.min(...values))}–${pct(Math.max(...values))}`
}
</script>

<template>
  <section class="focused-risk-path" aria-label="单链路风险演示">
    <header class="focused-path-heading"><div><span class="focused-path-kicker">单链路演示 · {{ path.order===2?'二阶':'一阶' }}{{ path.direction==='incoming'?'传入':'传出' }}</span><h3>{{ path.path }}</h3></div><div class="focused-path-actions"><button @click="$emit('fullscreen')">{{fullscreen?'退出全屏':'全屏看图'}}</button><button class="focused-path-back" @click="$emit('back')">返回图谱</button></div></header>
    <p class="focused-path-scenario" :class="{'is-stressed':stressed}">{{scenario}}<span v-if="stressed"> · 正常 → 压力对比</span><span v-else> · 当前情景数据</span></p>
    <div v-if="paths.length>1" class="focused-path-selector"><label :for="selectId">切换链路</label><select :id="selectId" :value="path.key" @change="$emit('select',$event.target.value)"><option v-for="item in paths" :key="item.key" :value="item.key">{{ item.direction==='incoming'?'传入':'传出' }} · {{ item.path }}</option></select></div>
    <div class="focused-path-flow" :class="{'is-stressed':stressed}" aria-label="风险沿链路的传导过程">
      <template v-for="(step,index) in path.steps" :key="`${path.key}-${scenario}-${index}`">
        <div v-if="index" class="focused-path-hop"><span>第{{index}}段</span><svg viewBox="0 0 48 24" aria-hidden="true"><path d="M2 12h40m-9-8 9 8-9 8"/></svg><button v-for="relation in step.relations" :key="relation.relation_id" :aria-label="`查看第${index}段${relation.relation_type}详情`" @click="$emit('inspect-edge',relation.relation_id)">{{relation.relation_type}}</button><small>强度 {{strength(step)}}</small></div>
        <article class="focused-path-card" :class="[level(step.node.risk),{'is-origin':step.role==='当前分析企业'}]" :style="{'--step-delay':`${index*100}ms`}">
          <span class="focused-path-role">{{step.role}}</span><button class="focused-path-company" @click="$emit('inspect',step.node.company_id)">{{step.node.company_name}}</button><p class="focused-path-product">{{step.node.product}}</p>
          <span class="focused-path-data-label">综合风险</span>
          <div class="focused-path-risk"><template v-if="stressed"><span>{{pct(step.node.baseline_risk)}}</span><i>→</i></template><strong>{{pct(step.node.risk)}}</strong></div>
          <b v-if="stressed" class="focused-path-change" :class="delta(step.node.risk,step.node.baseline_risk)<0?'relief':'increase'">变化 {{impact(delta(step.node.risk,step.node.baseline_risk))}} 个百分点</b>
          <div class="focused-path-detail-row"><span>自身风险</span><b><template v-if="stressed">{{pct(step.node.baseline_own_risk)}} → </template>{{pct(step.node.own_risk)}}</b></div>
          <div v-if="Number.isFinite(step.node.final_limit)" class="focused-path-detail-row"><span>建议额度</span><b><template v-if="stressed">{{money(step.node.baseline_final_limit)}} → </template>{{money(step.node.final_limit)}} 万元</b></div>
          <div v-if="index" class="focused-path-prefix" :class="step.prefix?.contribution<0?'relief':'increase'">
            <span>来自{{path.sourceName}}的{{index===2?'二阶':'一阶'}}净影响</span><b><template v-if="stressed">{{impact(step.prefix?.baseline_contribution)}} → </template>{{impact(step.prefix?.contribution)}} <small>个百分点</small></b>
          </div><div v-else class="focused-path-source">{{stressed?'正常情景 → 当前压力情景':'正常情景 · 链路起点'}}</div>
        </article>
      </template>
    </div>
    <footer class="focused-path-summary" :class="path.contribution<0?'relief':'increase'"><div><span>本链路对{{path.targetName}}的{{path.order===2?'二阶':'一阶'}}净影响</span><strong><template v-if="stressed"><em>{{impact(path.baseline_contribution)}}</em><i>→</i></template>{{impact(path.contribution)}} <small>个百分点</small></strong></div><b v-if="stressed">较正常 {{impact(pathChange)}} 个百分点</b></footer>
    <p class="focused-path-note">企业综合风险包含其他来源；链路贡献仅表示{{path.sourceName}}沿当前路径的影响。{{path.order===2?'第二段显示本源影响累计传到终点的二阶贡献。':''}}下方风险汇总仍采用完整网络结果。</p>
  </section>
</template>
