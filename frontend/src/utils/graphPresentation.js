import { filterRiskExplanation, networkView } from './networkView.js'

// Presentation only: never feed grouped nodes or edges back into risk calculations.
export function worseningSubjects(nodes, limit=3) {
  const level=risk=>risk>=.55?2:risk>=.35?1:0
  return nodes.filter(node=>node.risk!=null&&node.baseline_risk!=null).map(node=>({...node,change:Number(node.risk)-Number(node.baseline_risk)}))
    .filter(node=>Number.isFinite(node.change)&&node.change>=.00005)
    .sort((a,b)=>b.change-a.change||a.company_id.localeCompare(b.company_id))
    .slice(0,limit).map(node=>({...node,escalation:level(node.risk)>level(node.baseline_risk)?(level(node.risk)===2?'升至高风险':'升至中风险'):'风险上升'}))
}

export function stressPriorityIds(nodes) {
  const worsening=worseningSubjects(nodes,Infinity)
  return new Set([...worsening.slice(0,3),...worsening.filter(node=>node.escalation!=='风险上升')].map(node=>node.company_id))
}

export function keyRiskView(edges,origin,explanation,options={}) {
  const full=networkView(edges,origin,{...options,direction:'both'})
  if(!explanation?.incoming_paths||!explanation?.recipients)return full
  const filtered=filterRiskExplanation(explanation,edges,options)
  const paths=[...filtered.incoming.slice(0,3),...filtered.recipients.slice(0,3).map(recipient=>
    [...recipient.paths].sort((a,b)=>Math.abs(b.contribution)-Math.abs(a.contribution))[0]).filter(Boolean)]
  const ids=new Set(paths.flatMap(path=>path.relation_ids))
  const selected=networkView(edges.filter(edge=>ids.has(edge.relation_id)),origin,{...options,direction:'both'})
  return {...selected,is_key:true,selected_path_count:paths.length,total_subject_count:full.ids.size,total_relation_count:full.edges.length}
}

function cohort(node) {
  const product=node.product||''
  if(node.business_role==='steel') {
    if(/轧材|轧板材|型钢/.test(product))return ['rolling','轧制板型材']
    if(/特种钢材|钢管|金属制品|钢丝/.test(product))return ['processing','钢材深加工']
    if(/铸件|锻件/.test(product))return ['casting','铸锻加工']
  }
  if(node.business_role==='supplier') {
    if(/焦炭|废钢|铁矿石/.test(product))return ['raw','大宗原料']
    if(/铁合金|耐火材料/.test(product))return ['auxiliary','合金与耐材']
  }
  if(node.business_role==='customer'&&!/订单|贸易/.test(product))return ['manufacturing','制造客户']
  if(node.business_role==='materials') {
    if(/矿渣微粉|钢渣资源化|再生骨料/.test(product))return ['recycling','资源循环利用']
    if(/混凝土|墙材|装配式/.test(product))return ['building','建材与构件']
  }
  return null // Distinct energy and public facility services always stay identifiable.
}

export function businessGrouping(nodes,scope,origin,{enabled=true,expanded=new Set(),protectedIds=new Set()}={}) {
  const buckets=new Map(),mapping=new Map(nodes.map(node=>[node.company_id,node.company_id]))
  if(enabled)nodes.filter(node=>scope.ids.has(node.company_id)&&node.company_id!==origin&&!protectedIds.has(node.company_id)).forEach(node=>{
    const category=cohort(node)
    if(!category)return
    // Never merge first and second rings, or opposing directions of dependency.
    const key=`group:${node.business_role}:${category[0]}:${scope.depths?.get(node.company_id)??'park'}:${scope.roles?.get(node.company_id)||'park'}`
    if(!buckets.has(key))buckets.set(key,{id:key,label:category[1],members:[]})
    buckets.get(key).members.push(node)
  })
  const groups=new Map()
  for(const [id,group] of buckets)if(group.members.length>1&&!expanded.has(id)) {
    groups.set(id,group)
    group.members.forEach(node=>mapping.set(node.company_id,id))
  }
  return {mapping,groups}
}

export function groupedBusinessView(nodes,view,grouping) {
  const byId=new Map(nodes.map(node=>[node.company_id,node])),visible=new Map(),edgeBuckets=new Map(),internal=new Map()
  for(const id of view.ids) {
    const node=byId.get(id)
    if(!node)continue
    const key=grouping.mapping.get(id)||id
    if(!visible.has(key))visible.set(key,[])
    visible.get(key).push(node)
  }
  const projectedNodes=[...visible].map(([id,members])=>{
    const group=grouping.groups.get(id)
    if(!group)return members[0]
    return {...members[0],company_id:id,company_name:group.label,short_name:group.label==='资源循环利用'?'资源循环':group.label,
      is_group:true,members,member_count:members.length,product:`${members.length}家 · 最高风险 ${(Math.max(...members.map(n=>Number(n.risk)||0))*100).toFixed(1)}%`,
      risk:Math.max(...members.map(n=>Number(n.risk)||0)),risk_delta:0,can_analyze:false}
  })
  for(const edge of view.edges) {
    const source=grouping.mapping.get(edge.source)||edge.source,target=grouping.mapping.get(edge.target)||edge.target
    if(source===target) {if(!internal.has(source))internal.set(source,[]);internal.get(source).push(edge);continue}
    const merged=grouping.groups.has(source)||grouping.groups.has(target)
    const key=merged?`bundle:${source}:${target}:${edge.dependency_class}`:edge.relation_id
    if(!edgeBuckets.has(key))edgeBuckets.set(key,{...edge,relation_id:key,source,target,is_bundle:merged,relations:[]})
    edgeBuckets.get(key).relations.push(edge)
  }
  const edges=[...edgeBuckets.values()].map(edge=>({...edge,relation_count:edge.relations.length,
    relation_type:new Set(edge.relations.map(e=>e.relation_type)).size>1?'采购/销售依赖':edge.relation_type,
    min_weight:Math.min(...edge.relations.map(e=>Number(e.weight)||0)),max_weight:Math.max(...edge.relations.map(e=>Number(e.weight)||0)),
    // A bounded average controls line width only; it is not a new dependency probability.
    weight:edge.relations.reduce((sum,e)=>sum+Number(e.weight||0),0)/edge.relations.length}))
  const remap=map=>map&&new Map([...map].filter(([id])=>view.ids.has(id)).map(([id,value])=>[grouping.mapping.get(id)||id,value]))
  return {nodes:projectedNodes,view:{...view,ids:new Set(projectedNodes.map(n=>n.company_id)),edges,
    depths:remap(view.depths),roles:remap(view.roles),incomingDepths:remap(view.incomingDepths),outgoingDepths:remap(view.outgoingDepths)},internal,
    subject_count:view.ids.size,relation_count:view.edges.length}
}
