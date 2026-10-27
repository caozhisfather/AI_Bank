// Only select and present already-computed paths. No propagation is recalculated here.
export const riskPathKey = path => path.node_ids.join('>')

export function focusedRiskPaths(explanation, edges, { order='all', kind='all', relationIds=[] }={}) {
  const known=new Map(edges.map(edge=>[edge.relation_id,edge]))
  const clicked=new Set(relationIds)
  const unique=new Map()
  const add=(paths,direction)=>{
    for(const path of paths||[]) {
      if(!Array.isArray(path.node_ids)||path.node_ids.length<2||path.node_ids.length>3)continue
      if(order!=='all'&&path.order!==Number(order))continue
      const relations=(path.relation_ids||[]).map(id=>known.get(id)).filter(Boolean)
      // Reject incomplete/stale paths rather than drawing a made-up connecting segment.
      if(path.node_ids.slice(1).some((id,i)=>!relations.some(edge=>edge.source===path.node_ids[i]&&edge.target===id)))continue
      if(kind!=='all'&&!relations.some(edge=>edge.dependency_class===kind))continue
      if(clicked.size&&!relations.some(edge=>clicked.has(edge.relation_id)))continue
      const key=riskPathKey(path)
      if(!unique.has(key))unique.set(key,{...path,key,direction})
    }
  }
  add(explanation?.outgoing_paths||explanation?.recipients?.flatMap(item=>item.paths||[]),'outgoing')
  add(explanation?.incoming_paths,'incoming')
  return [...unique.values()].sort((a,b)=>b.order-a.order||Math.abs(b.contribution)-Math.abs(a.contribution)||a.key.localeCompare(b.key))
}

export function focusedRiskPathData(path, explanation, edges, nodes, origin) {
  if(!path)return null
  const byId=new Map(nodes.map(node=>[node.company_id,node]))
  const paths=[...(explanation?.incoming_paths||[]),...(explanation?.outgoing_paths||explanation?.recipients?.flatMap(item=>item.paths||[])||[])]
  const steps=path.node_ids.map((id,index)=>{
    const node=byId.get(id)
    if(!node)return null
    if(!index)return {node,index,role:id===origin?'当前分析企业':'影响来源',prefix:null,relations:[]}
    const source=path.node_ids[index-1]
    const relations=edges.filter(edge=>edge.source===source&&edge.target===id&&(path.relation_ids||[]).includes(edge.relation_id))
    const ids=path.node_ids.slice(0,index+1)
    let prefix=index===path.order?path:paths.find(item=>riskPathKey(item)===ids.join('>'))
    if(!prefix&&index===1) {
      // A one-hop prefix may not be anchored on the analysis enterprise. Its
      // backend direct channel contributions add up to the same one-hop path.
      const sum=key=>relations.every(edge=>Number.isFinite(edge[key]))?relations.reduce((total,edge)=>total+edge[key],0):null
      prefix={contribution:sum('direct_contribution'),baseline_contribution:sum('baseline_direct_contribution')}
    }
    return {node,index,role:id===origin?'当前分析企业':index===path.order?'受影响企业':'中间传导企业',prefix,relations}
  })
  if(steps.some(step=>!step))return null
  return {...path,steps,sourceName:steps[0].node.company_name,targetName:steps.at(-1).node.company_name}
}
