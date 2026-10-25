// Stored arrows: influencing subject -> dependent. Dependency view reverses only rendering.
export function directedPaths(edges, origin, order, incoming = true) {
  let paths = [[]]
  for (let step = 0; step < order; step++) {
    paths = paths.flatMap(path => {
      const endpoint = path.length ? (incoming ? path[0].source : path.at(-1).target) : origin
      return edges.filter(edge => (incoming ? edge.target : edge.source) === endpoint)
        .map(edge => incoming ? [edge, ...path] : [...path, edge])
    })
  }
  return paths
}

export function networkView(edges, origin, { order = 'all', kind = 'all', overview = false, direction = 'incoming' } = {}) {
  const orders = order === 'all' ? [1,2] : [Number(order)]
  const pathsFor = incoming => orders.flatMap(depth => directedPaths(edges,origin,depth,incoming)).filter(path=>kind==='all'||path.some(edge=>edge.dependency_class===kind))
  const incomingPaths = direction==='outgoing'?[]:pathsFor(true)
  const outgoingPaths = direction==='incoming'?[]:pathsFor(false)
  const matching = overview && order==='all' ? edges.filter(edge=>kind==='all'||edge.dependency_class===kind).map(edge=>[edge]) : [...incomingPaths,...outgoingPaths]
  const selected=new Map(), steps=new Map(), depths=new Map([[origin,0]])
  const incomingDepths=new Map(),outgoingDepths=new Map()
  incomingPaths.forEach(path=>path.forEach((edge,index)=>{
    const depth=path.length-index
    if(edge.source!==origin && (!incomingDepths.has(edge.source)||incomingDepths.get(edge.source)>depth)) incomingDepths.set(edge.source,depth)
  }))
  outgoingPaths.forEach(path=>path.forEach((edge,index)=>{
    const depth=index+1
    if(edge.target!==origin && (!outgoingDepths.has(edge.target)||outgoingDepths.get(edge.target)>depth)) outgoingDepths.set(edge.target,depth)
  }))
  matching.forEach(path=>path.forEach((edge,index)=>{
    selected.set(edge.relation_id,edge)
    if(!steps.has(edge.relation_id)) steps.set(edge.relation_id,new Set())
    steps.get(edge.relation_id).add(index+1)
  }))
  for(const [id,depth] of [...incomingDepths,...outgoingDepths]) if(!depths.has(id)||depths.get(id)>depth) depths.set(id,depth)
  const roles=new Map([[origin,'current']])
  for(const id of new Set([...incomingDepths.keys(),...outgoingDepths.keys()])) roles.set(id,incomingDepths.has(id)&&outgoingDepths.has(id)?'both':incomingDepths.has(id)?'incoming':'outgoing')
  return {edges:[...selected.values()],ids:new Set([origin,...[...selected.values()].flatMap(edge=>[edge.source,edge.target])]),steps,depths,incomingDepths,outgoingDepths,roles,pathCount:matching.length,incomingPaths,outgoingPaths}
}

export function dependencyEdges(edges) {
  return edges.map(edge=>({...edge,source:edge.dependent_id||edge.target,target:edge.provider_id||edge.source,risk_source:edge.source,risk_target:edge.target}))
}

export function directDependencyView(edges, origin, kind = 'all') {
  const direct = edges.filter(edge => (edge.source === origin || edge.target === origin) && (kind === 'all' || edge.dependency_class === kind))
  return { edges: dependencyEdges(direct), ids: new Set([origin, ...direct.flatMap(edge => [edge.source, edge.target])]) }
}

export function dependencyNeighborhoodView(edges, origin, kind = 'all') {
  // Follow each directed chain for two hops; sharing a provider alone is not a chain.
  const view = networkView(edges, origin, { direction: 'both', kind })
  return { ...view, edges: dependencyEdges(view.edges) }
}

function overviewGeometry(nodes) {
  const count=role=>nodes.filter(node=>node.business_role===role).length
  const bottom=Math.ceil(Math.max(390,190+Math.max(0,count('supplier')-1)*76+50,200+Math.max(0,count('customer')-1)*90+50,200+Math.max(0,Math.ceil(count('steel')/3)-1)*115+50)/10)*10
  return {materialsY:bottom+84,infraY:bottom+224,height:bottom+300}
}

export function networkHeight(nodes,view,mode) {
  if(mode==='dependency')return !view.depths&&nodes.some(node=>node.business_role)?overviewGeometry(nodes.filter(node=>view.ids.has(node.company_id))).height:540
  const counts=new Map()
  nodes.filter(node=>view.ids.has(node.company_id)).forEach(node=>{
    const role=view.roles?.get(node.company_id)
    const depth=role==='incoming'?view.incomingDepths.get(node.company_id):view.outgoingDepths?.get(node.company_id)
    const key=role==='both'?'both':`${role}${depth}`
    if(role&&role!=='current')counts.set(key,(counts.get(key)||0)+1)
  })
  const largest=Math.max(0,...[...counts].filter(([key])=>key!=='both').map(([,count])=>count))
  // Leave room for service labels and the red stress halo between rows.
  return Math.max(view.is_key?380:540,170+(largest+1)*76)+Math.max(0,Math.ceil((counts.get('both')||0)/7)-1)*68
}

export function networkLayout(nodes,view,origin,mode) {
  const visible=nodes.filter(node=>view.ids.has(node.company_id)).sort((a,b)=>a.company_id.localeCompare(b.company_id))
  if(mode==='dependency') {
    if(view.depths) {
      const first=visible.filter(node=>view.depths.get(node.company_id)===1)
      const second=visible.filter(node=>view.depths.get(node.company_id)===2)
      const angles=new Map(first.map((node,index)=>[node.company_id,-Math.PI/2+index/first.length*Math.PI*2]))
      const branches=new Map(first.map(node=>[node.company_id,[]]))
      second.forEach(node=>{
        const parent=first.find(item=>view.edges.some(edge=>(edge.source===item.company_id&&edge.target===node.company_id)||(edge.target===item.company_id&&edge.source===node.company_id)))
        if(parent)branches.get(parent.company_id).push(node)
      })
      // A utility hub may have many children. Spread the complete second ring
      // instead of squeezing them into one parent's narrow angular sector.
      const ordered=[...branches.values()].flat()
      second.filter(node=>!ordered.includes(node)).forEach(node=>ordered.push(node))
      ordered.forEach((node,index)=>angles.set(node.company_id,-Math.PI/2+index/ordered.length*Math.PI*2))
      const crowded=first.length>10
      return visible.map(node=>{
        const depth=view.depths.get(node.company_id)||0
        if(!depth)return {...node,x:420,y:270,r:36,role:'current',dependency_depth:0}
        const angle=angles.get(node.company_id)??0
        return {...node,x:420+Math.cos(angle)*(depth===1?(crowded?205:165):330),y:270+Math.sin(angle)*(depth===1?(crowded?140:115):210),r:depth===1?(crowded?21:25):22,dependency_depth:depth}
      })
    }
    if(visible.some(node=>node.business_role)) {
      const geometry=overviewGeometry(visible)
      const groups={supplier:[],steel:[],customer:[],materials:[],energy:[],infra:[]}
      visible.forEach(node=>groups[node.business_role]?.push(node))
      const locations=new Map()
      for(const [role,list] of Object.entries(groups))list.forEach((node,index)=>{
        let x,y
        if(role==='energy'){x=290+index*130;y=78}
        if(role==='infra'){x=230+index*190;y=geometry.infraY}
        if(role==='supplier'){x=105;y=190+index*76}
        if(role==='customer'){x=735;y=200+index*90}
        if(role==='steel'){x=285+index%3*135;y=200+Math.floor(index/3)*115}
        if(role==='materials'){x=420+(index-(list.length-1)/2)*Math.min(113,700/Math.max(1,list.length-1));y=geometry.materialsY}
        locations.set(node.company_id,{x,y})
      })
      return visible.map(node=>({...node,...(locations.get(node.company_id)||{x:420,y:460}),r:node.company_id===origin?31:25,role:node.company_id===origin?'current':undefined}))
    }
    const rest=visible.filter(node=>node.company_id!==origin),inner=rest.length>18?12:0
    return visible.map(node=>{
      if(node.company_id===origin) return {...node,x:420,y:270,r:inner?29:36,role:'current'}
      const index=rest.indexOf(node),inside=index<inner,count=inside?inner:rest.length-inner,position=inside?index:index-inner
      const angle=-Math.PI/2+position/Math.max(1,count)*Math.PI*2+(inside?.1:0)
      return {...node,x:420+Math.cos(angle)*(inside?155:inner?330:290),y:270+Math.sin(angle)*(inside?115:inner?205:175),r:inner?22:27}
    })
  }
  const groups={incoming1:[],incoming2:[],outgoing1:[],outgoing2:[],both:[]}
  visible.forEach(node=>{
    if(node.company_id===origin) return
    const role=view.roles.get(node.company_id)
    const depth=role==='incoming'?view.incomingDepths.get(node.company_id):view.outgoingDepths.get(node.company_id)
    groups[role==='both'?'both':`${role}${Math.min(2,depth)}`]?.push(node)
  })
  const height=networkHeight(nodes,view,mode)
  const positions=new Map([[origin,{x:420,y:height/2-20}]])
  for(const [key,list] of Object.entries(groups)) list.forEach((node,index)=>{
    const inRow=Math.min(7,list.length-Math.floor(index/7)*7)
    const x=key==='incoming1'?255:key==='incoming2'?85:key==='outgoing1'?585:key==='outgoing2'?755:420+(index%7-(inRow-1)/2)*90
    const y=key==='both'?height-70-Math.floor(index/7)*68:65+(index+1)*(height-170)/(list.length+1)
    positions.set(node.company_id,{x,y})
  })
  return visible.map(node=>({...node,...positions.get(node.company_id),r:node.company_id===origin?29:22,role:view.roles.get(node.company_id)}))
}

// Summarize already-computed path contributions for the current display filters.
export function filterRiskExplanation(explanation, edges, {order='all',kind='all'}={}) {
  const selectedIds=new Set(edges.filter(edge=>kind==='all'||edge.dependency_class===kind).map(edge=>edge.relation_id))
  const matches=path=>(order==='all'||path.order===Number(order))&&(kind==='all'||path.relation_ids.some(id=>selectedIds.has(id)))
  const incoming=(explanation.incoming_paths||[]).map((path,index)=>({...path,index})).filter(matches)
  const recipients=(explanation.recipients||[]).map(item=>{
    const paths=item.paths.filter(matches)
    return {...item,paths,contribution:paths.reduce((sum,path)=>sum+path.contribution,0),baseline_contribution:paths.reduce((sum,path)=>sum+path.baseline_contribution,0),delta:paths.reduce((sum,path)=>sum+path.delta,0),gross_contribution:paths.reduce((sum,path)=>sum+(path.gross_contribution||0),0),mitigation_contribution:paths.reduce((sum,path)=>sum+(path.mitigation_contribution||0),0)}
  }).filter(item=>item.paths.length).sort((a,b)=>Math.abs(b.contribution)-Math.abs(a.contribution)||a.company_id.localeCompare(b.company_id))
  return {incoming,recipients}
}
