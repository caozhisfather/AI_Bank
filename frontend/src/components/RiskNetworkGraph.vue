<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, useId, watch } from 'vue'
import { dependencyEdges, dependencyNeighborhoodView, networkHeight, networkLayout, networkView } from '../utils/networkView'
import { routeControlPoint } from '../utils/graphRoute'
import { graphTransitionFrame } from '../utils/graphTransition'
import { businessGrouping, groupedBusinessView, keyRiskView, stressPriorityIds, worseningSubjects } from '../utils/graphPresentation'
const props=defineProps({graph:{type:Object,default:()=>({nodes:[],edges:[]})},explanation:Object,selectedCompanyId:String,mode:{type:String,default:'dependency'},stressed:Boolean})
const emit=defineEmits(['inspect','filter','select'])
const graphId=`network-${useId().replace(/[^a-zA-Z0-9_-]/g,'')}`
const kind=ref('all'),order=ref('all'),hover=ref(null),hoverEdge=ref(null)
const businessScope=ref('direct')
const compact=ref(true),expanded=ref(new Set()),bundle=ref(null)
const graphStage=ref(null),fullscreen=ref(false),fullscreenError=ref('')
function syncFullscreen(){fullscreen.value=document.fullscreenElement===graphStage.value}
async function toggleFullscreen(){
  fullscreenError.value=''
  try {
    if(document.fullscreenElement===graphStage.value) await document.exitFullscreen()
    else if(graphStage.value?.requestFullscreen) await graphStage.value.requestFullscreen()
    else fullscreenError.value='当前浏览器暂不支持全屏，可收起筛选面板查看更多图谱。'
  } catch {fullscreenError.value='暂时无法进入全屏，可收起筛选面板查看更多图谱。'}
}
onMounted(()=>document.addEventListener('fullscreenchange',syncFullscreen))
onBeforeUnmount(()=>document.removeEventListener('fullscreenchange',syncFullscreen))
const defaultFilters=computed(()=>kind.value==='all'&&order.value==='all'&&businessScope.value==='direct'&&compact.value&&expanded.value.size===0)
function resetFilters(){
  kind.value='all';order.value='all';businessScope.value='direct';compact.value=true
  expanded.value=new Set();hover.value=null;hoverEdge.value=null;bundle.value=null
}
watch([kind,order],()=>emit('filter',{kind:kind.value,order:order.value}),{immediate:true})
const allNodes=computed(()=>props.graph.nodes||[]),rawEdges=computed(()=>props.graph.edges||[])
const origin=computed(()=>props.selectedCompanyId||allNodes.value.find(node=>node.selected)?.company_id)
const classes=computed(()=>props.graph.relation_classes||[])
const classMap=computed(()=>Object.fromEntries(classes.value.map(item=>[item.key,item])))
const business=computed(()=>props.mode==='dependency')
const filterSummary=computed(()=>[
  kind.value==='all'?'全部类型':classes.value.find(item=>item.key===kind.value)?.label||'已筛选',
  business.value?(businessScope.value==='overview'?'园区总览':'两阶依赖'):(order.value==='all'?'全部层级':`${order.value}阶传导`),
  compact.value?(business.value?'精简分组':'关键链路'):'全部展开'
].join(' · '))
const worsening=computed(()=>props.stressed?worseningSubjects(allNodes.value):[])
const topChanges=computed(()=>props.stressed?stressPriorityIds(allNodes.value):new Set())
watch([()=>props.mode,()=>props.selectedCompanyId],()=>{hover.value=null;hoverEdge.value=null;bundle.value=null})
watch([kind,order,businessScope,compact],()=>{hover.value=null;hoverEdge.value=null;bundle.value=null})
watch(()=>props.graph,()=>{bundle.value=null;hover.value=null;hoverEdge.value=null})
watch(()=>props.selectedCompanyId,()=>{expanded.value=new Set();bundle.value=null;if(business.value){kind.value='all';businessScope.value='direct'}})
const scope=computed(()=>business.value?(businessScope.value==='overview'?{edges:dependencyEdges(rawEdges.value),ids:new Set(allNodes.value.map(node=>node.company_id))}:dependencyNeighborhoodView(rawEdges.value,origin.value)):networkView(rawEdges.value,origin.value,{order:order.value,direction:'both'}))
const view=computed(()=>{
  if(!business.value) return compact.value?keyRiskView(rawEdges.value,origin.value,props.explanation,{order:order.value,kind:kind.value}):networkView(rawEdges.value,origin.value,{order:order.value,kind:kind.value,direction:'both'})
  if(businessScope.value==='overview'){
    const edges=scope.value.edges.filter(edge=>kind.value==='all'||edge.dependency_class===kind.value)
    return {edges,ids:kind.value==='all'?scope.value.ids:new Set([origin.value,...edges.flatMap(edge=>[edge.source,edge.target])])}
  }
  return dependencyNeighborhoodView(rawEdges.value,origin.value,kind.value)
})
const groupingScope=computed(()=>business.value?scope.value:view.value)
const grouping=computed(()=>businessGrouping(allNodes.value,groupingScope.value,origin.value,{enabled:compact.value,expanded:expanded.value,protectedIds:topChanges.value}))
const fullPresentation=computed(()=>groupedBusinessView(allNodes.value,groupingScope.value,grouping.value))
const presentation=computed(()=>groupedBusinessView(allNodes.value,view.value,grouping.value))
const renderView=computed(()=>presentation.value.view)
// Keep the six park zones fixed across category filters; reflow local filtered chains.
const layoutScope=computed(()=>business.value&&businessScope.value==='overview'?fullPresentation.value.view:renderView.value)
const targetCanvasHeight=computed(()=>networkHeight(fullPresentation.value.nodes,layoutScope.value,props.mode))
const crowdedRing=computed(()=>business.value&&[...(layoutScope.value.depths?.values()||[])].filter(depth=>depth===1).length>10)
const positions=computed(()=>new Map(networkLayout(fullPresentation.value.nodes,layoutScope.value,origin.value,props.mode).map(node=>[node.company_id,node])))
const targetNodes=computed(()=>presentation.value.nodes.filter(node=>positions.value.has(node.company_id)).map(node=>({...positions.value.get(node.company_id),...node,focus:node.company_id===origin.value?1:0,opacity:1})))
const displayed=shallowRef({nodes:[],edges:[],height:540})
const canvasHeight=computed(()=>displayed.value.height??targetCanvasHeight.value)
let animationFrame=0,lastMode=props.mode
watch(()=>({nodes:targetNodes.value,edges:renderView.value.edges.map(edge=>({...edge,opacity:1})),height:targetCanvasHeight.value,mode:props.mode}),target=>{
  cancelAnimationFrame(animationFrame)
  const next={nodes:target.nodes,edges:target.edges,height:target.height}
  const animate=lastMode===props.mode&&displayed.value.nodes.length&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches
  lastMode=props.mode
  if(!animate){displayed.value=next;return}
  const from=displayed.value,start=performance.now()
  function tick(now){
    const progress=Math.min(1,(now-start)/950)
    const eased=progress*progress*(3-2*progress)
    displayed.value=graphTransitionFrame(from,next,eased)
    if(progress<1)animationFrame=requestAnimationFrame(tick)
  }
  animationFrame=requestAnimationFrame(tick)
},{immediate:true})
onBeforeUnmount(()=>cancelAnimationFrame(animationFrame))
const nodes=computed(()=>displayed.value.nodes)
const byId=computed(()=>Object.fromEntries(nodes.value.map(node=>[node.company_id,node])))
const count=key=>scope.value.edges.filter(edge=>edge.dependency_class===key).length
const pct=value=>`${(Number(value||0)*100).toFixed(1)}%`
const effect=value=>`${Number(value)<0?'−':'+'}${Math.abs(Number(value||0)*100).toFixed(2)}`
const pp=value=>`${value>=0?'+':'−'}${Math.abs(Number(value||0)*100).toFixed(2)}个百分点`
const color=risk=>risk>=.55?'#a71930':risk>=.35?'#bf8431':'#17805c'
const stressedEdges=computed(()=>{
  const keyRelations=new Set(view.value.edges.filter(edge=>(topChanges.value.has(edge.source)||topChanges.value.has(edge.target))&&edge.contribution_delta>1e-7).sort((a,b)=>b.contribution_delta-a.contribution_delta).slice(0,5).map(edge=>edge.relation_id))
  return new Set(renderView.value.edges.filter(edge=>keyRelations.has(edge.relation_id)||edge.relations?.some(item=>keyRelations.has(item.relation_id))).map(edge=>edge.relation_id))
})
const connected=computed(()=>new Set(hover.value?renderView.value.edges.filter(edge=>edge.source===hover.value||edge.target===hover.value).map(edge=>edge.relation_id):renderView.value.edges.map(edge=>edge.relation_id)))
const edges=computed(()=>{
  const groups=new Map()
  displayed.value.edges.forEach(edge=>{
    const key=[edge.source,edge.target].sort().join('|')
    if(!groups.has(key)) groups.set(key,[])
    groups.get(key).push(edge)
  })
  const result=[]
  groups.forEach(group=>group.sort((a,b)=>a.relation_id.localeCompare(b.relation_id)).forEach((edge,index)=>{
    const from=byId.value[edge.source],to=byId.value[edge.target]
    if(!from||!to) return
    const {x:cx,y:cy}=routeControlPoint(from,to,(index-(group.length-1)/2)*36,nodes.value,canvasHeight.value)
    const a=Math.hypot(cx-from.x,cy-from.y)||1,b=Math.hypot(to.x-cx,to.y-cy)||1
    const sx=from.x+(cx-from.x)/a*(from.r+9),sy=from.y+(cy-from.y)/a*(from.r+9)
    const tx=to.x-(to.x-cx)/b*(to.r+12),ty=to.y-(to.y-cy)/b*(to.r+12)
    result.push({...edge,d:`M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`,labelX:(sx+2*cx+tx)/4,labelY:(sy+2*cy+ty)/4-9,step:!business.value&&order.value==='2'?`第${[...(view.value.steps.get(edge.relation_id)||[])].sort().join('/')}段`:''})
  }))
  return result
})
const edgeName=edge=>`${byId.value[edge.source]?.company_name} → ${byId.value[edge.target]?.company_name}`
const strength=edge=>edge.is_bundle?`${edge.relation_count}条关系 · 强度 ${pct(edge.min_weight)}–${pct(edge.max_weight)}`:`依赖强度 ${pct(edge.weight)}`
const rawName=id=>allNodes.value.find(node=>node.company_id===id)?.company_name||id
const short=name=>name?.length>9?`${name.slice(0,8)}…`:name
const roleName={current:'当前企业',incoming:'风险来源',outgoing:'受影响主体',both:'双向关联'}
const pending=computed(()=>(props.graph.pending_edges||[]).filter(edge=>!business.value||businessScope.value==='overview'||(scope.value.ids.has(edge.source)&&scope.value.ids.has(edge.target))))
function activateNode(node){
  if(node.is_group){expanded.value=new Set([...expanded.value,node.company_id]);bundle.value=null;hover.value=null;return}
  if(business.value&&(node.can_analyze||node.node_type==='enterprise')){
    if(node.company_id!==origin.value)emit('select',node.company_id)
    else {businessScope.value='direct';kind.value='all'}
  }else emit('inspect',{type:'node',id:node.company_id})
}
function activateEdge(edge){if(edge.is_bundle)bundle.value=edge;else emit('inspect',{type:'edge',id:edge.relation_id})}
</script>
<template>
  <section class="risk-graph-shell" :class="{'business-network':business,'has-stress':stressed}" :aria-label="business?'业务依赖关系图':'双向风险传导图'">
    <section v-if="stressed" class="graph-stress-focus" aria-label="园区主要恶化企业"><div class="graph-stress-focus-heading"><b>园区主要恶化企业</b><span>按综合风险增幅排序 · 相比正常情景</span></div><div v-if="worsening.length" class="graph-stress-cards"><button v-for="(node,index) in worsening" :key="node.company_id" @click="emit('select',node.company_id)"><span class="graph-stress-rank">0{{index+1}}</span><b>{{node.company_name}}</b><strong>{{pp(node.change)}}</strong><span>{{pct(node.baseline_risk)}} → {{pct(node.risk)}}</span><small>{{node.escalation}} · 点击分析</small></button></div><p v-else>当前情景暂无风险上升主体。</p></section>
    <div ref="graphStage" class="graph-stage">
      <button type="button" class="graph-expand-button" @click="toggleFullscreen" :aria-label="fullscreen?'退出全屏图谱':'全屏查看图谱'">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path v-if="!fullscreen" d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4"/><path v-else d="M3 7h4V3m6 0v4h4M7 17v-4H3m10 4v-4h4"/></svg>
        {{fullscreen?'退出全屏':'全屏看图'}}
      </button>
      <details class="graph-floating-controls" @keydown.esc.stop="event=>event.currentTarget.open=false">
        <summary class="graph-controls-toggle">
          <svg class="graph-controls-symbol" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></svg>
          <span><b>图谱筛选</b><small>{{filterSummary}}</small></span>
          <svg class="graph-controls-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg>
        </summary>
        <div class="graph-controls-content">
    <div class="directed-graph-toolbar">
      <span class="graph-control-label">关系类型</span>
      <div class="relation-filters" role="group" aria-label="依赖关系筛选">
        <button type="button" :class="{active:kind==='all'}" :aria-pressed="kind==='all'" title="显示所有类型的关联关系" @click="kind='all'">全部类型 <small>{{scope.edges.length}}</small></button>
        <button v-for="item in classes" :key="item.key" type="button" :class="{active:kind===item.key}" :aria-pressed="kind===item.key" :title="`仅显示${item.label}`" @click="kind=item.key"><svg width="23" height="10" aria-hidden="true"><line x1="0" x2="23" y1="5" y2="5" :stroke="item.color" :stroke-dasharray="item.dash" stroke-width="2" /></svg>{{item.label}} <small>{{count(item.key)}}</small></button>
      </div>
      <button type="button" class="graph-reset-button" :disabled="defaultFilters" title="恢复全部类型、默认范围与分组展示" @click="resetFilters"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 8a7 7 0 1 1 1 7M3 3v5h5" /></svg>恢复默认</button>
    </div>
    <div v-if="business" class="propagation-order-toolbar">
      <span class="graph-control-label">显示范围</span>
      <div class="graph-business-scope" role="group" aria-label="业务依赖图范围">
        <button type="button" :class="{active:businessScope==='overview'}" :aria-pressed="businessScope==='overview'" title="查看园区内全部企业及关联关系" @click="businessScope='overview';hover=null">园区总览</button>
        <button type="button" :class="{active:businessScope==='direct'}" :aria-pressed="businessScope==='direct'" title="聚焦当前企业的一阶、二阶依赖关系" @click="businessScope='direct'">当前企业两阶依赖</button>
      </div>
      <span class="graph-control-hint">{{businessScope==='overview'?'查看园区全貌，点击企业可聚焦其关联关系':'以当前企业为中心，内圈为一阶、外圈为二阶关联'}}</span>
    </div>
    <div v-if="!business" class="propagation-order-toolbar"><span class="graph-control-label">传播层级</span><div class="graph-scope-buttons" role="group" aria-label="传播层级"><button v-for="item in [{key:'all',label:'全部层级'},{key:'1',label:'一阶传导'},{key:'2',label:'二阶传导'}]" :key="item.key" type="button" :class="{active:order===item.key}" :aria-pressed="order===item.key" @click="order=item.key">{{item.label}}</button></div><span class="graph-control-hint">同时查看风险传入与传出</span></div>
    <div class="graph-group-toolbar">
      <span class="graph-control-label">{{business?'企业展示':'图谱内容'}}</span>
      <div class="graph-scope-buttons" role="group" aria-label="企业分组展示">
        <button type="button" :class="{active:compact}" :aria-pressed="compact" title="优先显示分组与主要关联，减少图谱拥挤" @click="compact=true;expanded=new Set()">{{business?'精简分组':'关键链路'}}</button>
        <button type="button" :class="{active:!compact}" :aria-pressed="!compact" title="展开当前范围内全部企业及关联关系" @click="compact=false">{{business?'展开全部':'全部链路'}}</button>
      </div>
      <span class="graph-control-hint">{{business?(compact?'同类外围企业合并显示，点击分组即可展开':'当前范围内的企业逐一显示，可切回分组减少拥挤'):(compact?'显示主要传入与传出链路，点击分组可展开':'显示当前筛选下的完整传入与传出链路')}}</span>
      <button v-if="compact&&expanded.size" type="button" class="graph-reset-button" @click="expanded=new Set()">重新合并分组</button>
    </div>
        </div>
      </details>
    <div class="directed-graph-canvas">
      <svg class="risk-graph" :viewBox="`0 0 840 ${canvasHeight}`" preserveAspectRatio="xMidYMid meet" role="img" :aria-label="business?'园区业务依赖关系图':'园区风险传导图'">
        <g v-if="business&&businessScope==='overview'" class="overview-sections" aria-hidden="true"><rect x="220" y="28" width="400" height="100" rx="12"/><text x="420" y="20">能源服务</text><rect x="40" y="150" width="130" :height="Math.max(0,canvasHeight-450)" rx="12"/><text x="105" y="142">原料与生产配套</text><rect x="220" y="150" width="400" :height="Math.max(0,canvasHeight-450)" rx="12"/><text x="420" y="142">钢铁与金属加工</text><rect x="670" y="150" width="130" :height="Math.max(0,canvasHeight-450)" rx="12"/><text x="735" y="142">下游客户</text><rect x="32" :y="canvasHeight-265" width="776" height="100" rx="12"/><text x="420" :y="canvasHeight-273">建材与资源利用</text><rect x="156" :y="canvasHeight-125" width="530" height="100" rx="12"/><text x="420" :y="canvasHeight-133">公共设施服务</text></g>
        <defs><marker v-for="item in classes" :key="item.key" :id="`${graphId}-${item.key}`" markerWidth="10" markerHeight="10" refX="9" refY="5" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L0,10 L9,5 z" :fill="item.color" /></marker></defs>
        <g v-if="!business" class="risk-zone-labels" aria-hidden="true"><text x="160" y="48" text-anchor="middle">风险传入</text><text x="420" y="48" text-anchor="middle">当前分析企业</text><text x="680" y="48" text-anchor="middle">风险传出</text><line x1="340" x2="340" y1="75" :y2="canvasHeight-130"/><line x1="500" x2="500" y1="75" :y2="canvasHeight-130"/></g>
        <g :class="{'dependency-morph-scene':business}">
        <g v-if="business&&businessScope==='direct'" class="dependency-orbits" aria-hidden="true"><ellipse cx="420" cy="270" :rx="crowdedRing?205:165" :ry="crowdedRing?140:115"/><ellipse cx="420" cy="270" rx="330" ry="210"/></g>
        <g v-for="edge in edges" :key="`${mode}-${edge.relation_id}`" class="directed-edge" :style="{opacity:edge.opacity,pointerEvents:edge.opacity<.95?'none':undefined}" :class="{dimmed:!connected.has(edge.relation_id), 'stress-edge':stressed&&stressedEdges.has(edge.relation_id),'primary-edge':business&&(hover?(edge.source===hover||edge.target===hover):(edge.source===origin||edge.target===origin))}" role="button" :tabindex="edge.opacity<.95?-1:0" :aria-hidden="edge.opacity<.95?true:undefined" :aria-label="`${edgeName(edge)}，${edge.relation_type}，${strength(edge)}`" @mouseenter="hoverEdge=edge.relation_id" @mouseleave="hoverEdge=null" @focus="hoverEdge=edge.relation_id" @blur="hoverEdge=null" @click="activateEdge(edge)" @keydown.enter.prevent="activateEdge(edge)">
          <path :d="edge.d" class="directed-edge-line" :stroke="classMap[edge.dependency_class]?.color" :stroke-dasharray="classMap[edge.dependency_class]?.dash" :stroke-width="business?1+edge.weight*1.5:1.3+edge.weight*3" :marker-end="`url(#${graphId}-${edge.dependency_class})`"/><path :d="edge.d" class="directed-edge-hit"/>
          <text v-if="business&&hoverEdge===edge.relation_id" :x="edge.labelX" :y="edge.labelY" text-anchor="middle" class="edge-business-label">{{edge.is_bundle?strength(edge):`${edge.commodity||edge.relation_type} · ${pct(edge.weight)}`}}</text>
          <text v-if="!business&&edge.is_bundle" :x="edge.labelX" :y="edge.labelY" text-anchor="middle" class="net-path-label bundled-risk-label">{{edge.relation_count}}条关联</text><text v-else-if="!business" :x="edge.labelX" :y="edge.labelY" text-anchor="middle" class="net-path-label" :class="edge.direct_contribution<0?'risk-relief':'risk-increase'">{{effect(edge.direct_contribution)}}{{edge.step?` · ${edge.step}`:''}}</text><title>{{edgeName(edge)}} · {{edge.relation_type}} · {{strength(edge)}}</title>
        </g>
        <g v-for="node in nodes" :key="node.company_id" class="graph-node" :class="{selected:node.company_id===origin,'grouped-node':node.is_group,'stress-priority':stressed&&topChanges.has(node.company_id)}" :style="{opacity:node.opacity,pointerEvents:node.opacity<.95?'none':undefined}" :transform="`translate(${node.x} ${node.y})`" role="button" :tabindex="node.opacity<.95?-1:0" :aria-hidden="node.opacity<.95?true:undefined" :aria-label="node.is_group?`${node.company_name}，${node.member_count}家企业，点击展开，成员最高风险 ${pct(node.risk)}`:`${node.company_name}，${roleName[node.role]||'企业'}，综合风险 ${pct(node.risk)}${stressed&&topChanges.has(node.company_id)?`，主要恶化企业，风险上升 ${pp(node.risk_delta)}`:''}`" @mouseenter="hover=node.company_id" @mouseleave="hover=null" @focus="hover=node.company_id" @blur="hover=null" @click="activateNode(node)" @keydown.enter.prevent="activateNode(node)" @keydown.space.prevent="activateNode(node)">
          <circle :r="node.r+7" class="node-halo"/><circle v-if="stressed&&topChanges.has(node.company_id)" :r="node.r+12" class="stress-priority-ring"/><circle v-if="node.is_group" :r="node.r" cx="5" cy="-5" class="group-stack"/>
          <circle v-if="business" :r="node.r+7" class="node-focus-ring" :opacity="node.focus"/>
          <rect v-if="node.node_type==='energy'" :x="-node.r" :y="-node.r" :width="node.r*2" :height="node.r*2" rx="5" class="node-body" :fill="color(node.risk)"/>
          <path v-else-if="node.node_type==='infra'" :d="`M 0 ${-node.r-3} L ${node.r+3} 0 L 0 ${node.r+3} L ${-node.r-3} 0 Z`" class="node-body" :fill="color(node.risk)"/>
          <circle v-else :r="node.r" class="node-body" :fill="color(node.risk)"/>
          <text y="4" text-anchor="middle" :style="{fontSize:`${business?(node.short_name?.length>4?8:9)+2*node.focus:(node.company_id===origin?12:node.short_name?.length>4?8:10)}px`}">{{node.short_name||node.company_id}}</text><text :y="node.r+17" text-anchor="middle" class="node-label">{{node.is_group?node.product:short(node.product||node.company_name)}}</text>
          <g v-if="node.is_group" class="group-count"><circle :cx="node.r-1" :cy="-node.r+1" r="9"/><text :x="node.r-1" :y="-node.r+4" text-anchor="middle">{{node.member_count}}</text></g>
          <g v-if="stressed&&topChanges.has(node.company_id)" class="stress-priority-badge"><circle :cx="node.r" :cy="-node.r" r="9"/><text :x="node.r" :y="-node.r+4" text-anchor="middle">!</text></g>
          <text v-if="node.role==='both'" :y="node.r+31" text-anchor="middle" class="node-role-label">双向关联</text>
          <text v-if="!business&&node.company_id===origin" :y="node.r+32" text-anchor="middle" class="node-net-label" :class="node.network_risk<node.own_risk?'risk-relief':'risk-increase'">{{node.network_risk<node.own_risk?'园区净缓释':'园区净传入'}} {{effect(node.network_risk-node.own_risk)}}</text>
          <text v-if="stressed&&(node.company_id===origin||(business&&topChanges.has(node.company_id)))&&node.role!=='both'" :y="node.r+(!business&&node.company_id===origin?47:32)" text-anchor="middle" class="node-delta-label" :class="{decrease:node.risk_delta<0}">{{pp(node.risk_delta)}}</text>
          <title>{{node.is_group?`${node.company_name} · ${node.member_count}家，颜色为成员最高风险，点击展开`:`${node.company_name} · 正常 ${pct(node.baseline_risk)} · 当前 ${pct(node.risk)}`}}</title>
        </g>
        </g>
      </svg>
      <p v-if="!edges.length" class="graph-empty">当前筛选没有可展示的{{business?'依赖关系':'传入或传出路径'}}。</p>
    </div>
    <div class="directed-graph-legend"><div class="directed-node-legend"><span><i class="low"></i>低风险</span><span><i class="medium"></i>中风险</span><span><i class="high"></i>高风险</span></div><span>{{stressed?'节点颜色为压力情景风险':'节点颜色为正常情景风险'}} · {{compact?'分组取成员最高风险':'线宽为依赖强度'}} · 方形：能源 · 菱形：设施</span></div>
    </div>
    <p v-if="fullscreenError" class="graph-fullscreen-error" role="status">{{fullscreenError}}</p>
    <p class="directed-graph-guide">{{business?(businessScope==='overview'?'依赖方 → 被依赖方；当前为园区总览，点击企业查看其两阶依赖关系。':'依赖方 → 被依赖方；展示与目标企业相连的一、二阶依赖链，点击企业切换分析对象。'):'影响来源 → 当前企业 → 受影响主体；绿色负值为园区缓释，红色正值为风险传入，单位为百分点。'}}</p>
    <div v-if="bundle" class="graph-bundle-detail" aria-label="分组合并关系明细"><div><b>{{edgeName(bundle)}} · {{bundle.relation_count}}条成员关系</b><button aria-label="关闭分组关系明细" @click="bundle=null">×</button></div><p>{{business?'箭头为依赖方向；分组不代表成员之间可以互相替代。':'箭头为风险影响方向；每条成员连线保留独立贡献。'}}</p><ul><li v-for="relation in bundle.relations" :key="relation.relation_id"><span>{{rawName(relation.source)}} → {{rawName(relation.target)}}<small>{{relation.commodity||relation.relation_type}} · {{pct(relation.weight)}}<template v-if="!business"> · 净影响 {{pp(relation.direct_contribution)}}</template></small></span><button class="park-text-button" @click="emit('inspect',{type:'edge',id:relation.relation_id})">查看</button></li></ul></div>
    <div class="directed-graph-inspector"><div><b v-if="compact">{{targetNodes.length}} 个图示节点 · {{renderView.edges.length}} 条图示连线 · 覆盖 {{presentation.subject_count}} 个主体 / {{presentation.relation_count}} 条关系</b><b v-else>{{targetNodes.length}} 个主体 · {{view.edges.length}} 条关系</b><span>{{business?'深色为当前企业直接关系；悬停主体突出连线；点击切换分析':'点击节点或连线查看详情'}}</span></div><p v-if="compact">分组颜色取成员最高风险；点击合并连线查看原始成员。<template v-if="!business">当前为关键链路，完整范围含 {{view.total_subject_count||scope.ids.size}} 个主体、{{view.total_relation_count??scope.edges.length}} 条关系；风险汇总不受精简影响，下方明细保留当前筛选范围。</template><template v-else>风险与授信仍逐企业计算。</template></p></div>
    <details v-if="pending.length" class="pending-relations"><summary>{{pending.length}} 条关系待核验</summary><div class="table-wrap"><table><thead><tr><th>关系端点</th><th>原类型</th><th>待核验原因</th></tr></thead><tbody><tr v-for="item in pending" :key="item.relation_id"><td>{{item.source_name}} — {{item.target_name}}</td><td>{{item.original_relation_type}}</td><td>{{item.pending_reason}}</td></tr></tbody></table></div></details>
  </section>
</template>
