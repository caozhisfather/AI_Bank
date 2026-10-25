const mix=(a,b,t)=>a+(b-a)*t

// Rebase on the displayed frame so a second click never jumps back to an old layout.
export function graphTransitionFrame(from,to,progress) {
  const t=Math.max(0,Math.min(1,progress))
  if(t===1)return to
  const oldNodes=new Map(from.nodes.map(node=>[node.company_id,node]))
  const nextNodes=new Map(to.nodes.map(node=>[node.company_id,node]))
  const nodes=[...new Set([...oldNodes.keys(),...nextNodes.keys()])].map(id=>{
    const old=oldNodes.get(id),next=nextNodes.get(id),base=next||old
    const start=old||{...next,y:Number.isFinite(from.height)?Math.min(next.y,from.height-50):next.y,opacity:0,r:next.r*.85,focus:0}
    const end=next||{...old,y:Number.isFinite(to.height)?Math.min(old.y,to.height-50):old.y,opacity:0,r:old.r*.9,focus:0}
    return {...base,x:mix(start.x,end.x,t),y:mix(start.y,end.y,t),r:mix(start.r,end.r,t),
      opacity:mix(start.opacity??1,end.opacity??1,t),focus:mix(start.focus??0,end.focus??0,t),
      risk:mix(start.risk??0,end.risk??0,t)}
  })
  const oldEdges=new Map(from.edges.map(edge=>[edge.relation_id,edge]))
  const nextEdges=new Map(to.edges.map(edge=>[edge.relation_id,edge]))
  const edges=[...new Set([...oldEdges.keys(),...nextEdges.keys()])].map(id=>{
    const old=oldEdges.get(id),next=nextEdges.get(id)
    return {...(next||old),opacity:mix(old?(old.opacity??1):0,next?(next.opacity??1):0,t)}
  })
  const geometry=Number.isFinite(from.height)||Number.isFinite(to.height)?{height:mix(from.height??to.height,to.height??from.height,t)}:{}
  return {nodes,edges,...geometry}
}
