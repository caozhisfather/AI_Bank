import test from 'node:test'
import assert from 'node:assert/strict'
import { dependencyEdges, dependencyNeighborhoodView, directDependencyView, filterRiskExplanation, networkHeight, networkLayout, networkView } from '../frontend/src/utils/networkView.js'
import { routeControlPoint } from '../frontend/src/utils/graphRoute.js'
import { graphTransitionFrame } from '../frontend/src/utils/graphTransition.js'
import { businessGrouping, groupedBusinessView, keyRiskView, stressPriorityIds, worseningSubjects } from '../frontend/src/utils/graphPresentation.js'
import { effectLabel,signedImpact } from '../frontend/src/utils/riskDisplay.js'
const edge = (source, target, dependency_class = 'supply') => ({ source, target, dependency_class, relation_id: `${source}-${target}-${dependency_class}` })
const edges = [edge('U', 'M', 'energy'), edge('M', 'A'), edge('A', 'B', 'energy'), edge('B', 'C'), edge('C', 'H'), edge('M', 'S'), edge('Z', 'B')]

test('business display groups peers but preserves individual source services, selected and stressed subjects',()=>{
  const nodes=[{company_id:'A',business_role:'steel',product:'热轧板材'},...['B','C','D'].map(company_id=>({company_id,business_role:'steel',product:'冷轧板材',risk:.2})),{company_id:'GAS',business_role:'energy',product:'天然气'},{company_id:'WATER',business_role:'infra',product:'工业用水'}]
  const scope={ids:new Set(nodes.map(n=>n.company_id)),edges:[]}
  const grouping=businessGrouping(nodes,scope,'A',{protectedIds:new Set(['D'])})
  assert.equal(grouping.mapping.get('A'),'A')
  assert.equal(grouping.mapping.get('D'),'D')
  assert.equal(grouping.mapping.get('GAS'),'GAS')
  assert.equal(grouping.mapping.get('WATER'),'WATER')
  assert.equal(grouping.mapping.get('B'),grouping.mapping.get('C'))
  const expanded=businessGrouping(nodes,scope,'A',{expanded:new Set(grouping.groups.keys())})
  assert.equal(expanded.groups.size,0)
  assert.equal(businessGrouping(nodes,scope,'A',{enabled:false}).groups.size,0)
})

test('grouped connections preserve every original relation, direction and class without summing probabilities',()=>{
  const nodes=[{company_id:'A',risk:.16},...['B','C'].map((company_id,i)=>({company_id,business_role:'steel',product:'钢管',risk:.2+i*.4}))]
  const raw=[{...edge('A','B'),weight:.7},{...edge('A','C'),weight:.6},{...edge('C','A','energy'),weight:.5},{...edge('B','C'),weight:.2}]
  const view={ids:new Set(nodes.map(n=>n.company_id)),edges:raw}
  const snapshot=JSON.stringify({nodes,raw})
  const result=groupedBusinessView(nodes,view,businessGrouping(nodes,view,'A'))
  assert.equal(result.nodes.length,2)
  const group=result.nodes.find(n=>n.is_group)
  assert.ok(Math.abs(group.risk-.6)<1e-12)
  assert.equal(group.member_count,2)
  const outward=result.view.edges.find(e=>e.source==='A')
  assert.equal(outward.relations.length,2)
  assert.ok(Math.abs(outward.weight-.65)<1e-12)
  assert.equal(outward.min_weight,.6)
  assert.equal(outward.max_weight,.7)
  assert.equal(result.view.edges.find(e=>e.target==='A').dependency_class,'energy')
  assert.equal(result.view.edges.reduce((sum,e)=>sum+e.relations.length,0)+[...result.internal.values()].flat().length,raw.length)
  assert.equal(JSON.stringify({nodes,raw}),snapshot)
})

test('local grouping never merges different dependency rings or opposing roles',()=>{
  const nodes=['A','B','C','D','E'].map(company_id=>({company_id,business_role:'customer',product:'机械装备'}))
  const scope={ids:new Set(nodes.map(n=>n.company_id)),edges:[],depths:new Map([['A',0],['B',1],['C',1],['D',2],['E',1]]),roles:new Map([['A','current'],['B','incoming'],['C','incoming'],['D','incoming'],['E','outgoing']])}
  const grouped=businessGrouping(nodes,scope,'A')
  assert.equal(grouped.mapping.get('B'),grouped.mapping.get('C'))
  assert.notEqual(grouped.mapping.get('B'),grouped.mapping.get('D'))
  assert.notEqual(grouped.mapping.get('B'),grouped.mapping.get('E'))
  const filtered={...scope,ids:new Set(['A','B'])}
  const projection=groupedBusinessView(nodes,filtered,grouped)
  assert.equal(projection.nodes.find(n=>n.is_group).member_count,1)
  assert.equal(projection.view.depths.get(grouped.mapping.get('B')),1)
})

test('stress highlights rank worsening rather than high baseline or improving risks',()=>{
  const nodes=[{company_id:'HIGH',risk:.8,baseline_risk:.8},{company_id:'IMPROVE',risk:.2,baseline_risk:.5},{company_id:'MED',risk:.4,baseline_risk:.2},{company_id:'CROSS',risk:.6,baseline_risk:.5},{company_id:'INCREASE',risk:.2,baseline_risk:.15}]
  const focus=worseningSubjects(nodes)
  assert.deepEqual(focus.map(n=>n.company_id),['MED','CROSS','INCREASE'])
  assert.equal(focus[0].escalation,'升至中风险')
  assert.equal(focus[1].escalation,'升至高风险')
  assert.deepEqual(worseningSubjects([{company_id:'A',risk:.1,baseline_risk:.2}]),[])
  const lowerRankCrossing={company_id:'UPGRADE',risk:.56,baseline_risk:.54}
  assert.ok(stressPriorityIds([...nodes,lowerRankCrossing]).has('UPGRADE'))
})

test('a compact overview keeps six role zones while removing empty vertical space',()=>{
  const nodes=[...Array.from({length:12},(_,i)=>({company_id:`S${i}`,business_role:'steel',product:'钢管',risk:.2})),...['supplier','customer','materials','energy','infra'].map((business_role,i)=>({company_id:`R${i}`,business_role,product:'独立服务',risk:.1}))]
  const view={ids:new Set(nodes.map(n=>n.company_id)),edges:[]}
  const compact=groupedBusinessView(nodes,view,businessGrouping(nodes,view,'S0'))
  assert.ok(networkHeight(compact.nodes,compact.view,'dependency')<networkHeight(nodes,view,'dependency'))
  const layout=networkLayout(compact.nodes,compact.view,'S0','dependency')
  assert.ok(layout.find(n=>n.business_role==='energy').y<150)
  assert.ok(layout.find(n=>n.business_role==='infra').y>layout.find(n=>n.business_role==='materials').y)
  assert.ok(layout.every(n=>n.y+n.r+32<networkHeight(compact.nodes,compact.view,'dependency')))
})

test('key risk view selects complete backend paths and never changes their computed contributions',()=>{
  const relations=[...['S1','S2','S3','S4'].map(id=>({...edge(id,'A'),weight:.2})),{...edge('ENERGY','S1','energy'),weight:.3},...['R1','R2','R3','R4'].map(id=>({...edge('A',id),weight:.2}))]
  const path=(ids,value)=>({node_ids:ids,order:ids.length-1,contribution:value,baseline_contribution:value,delta:0,relation_ids:ids.slice(1).map((id,i)=>relations.find(e=>e.source===ids[i]&&e.target===id).relation_id)})
  const incoming=[path(['S1','A'],.04),path(['S2','A'],.03),path(['ENERGY','S1','A'],.02),path(['S4','A'],.01)]
  const recipients=['R1','R2','R3','R4'].map((company_id,i)=>({company_id,paths:[path(['A',company_id],.05-i*.01)]}))
  const explanation={incoming_paths:incoming,recipients}
  const snapshot=JSON.stringify(explanation)
  const key=keyRiskView(relations,'A',explanation)
  assert.ok(key.ids.has('ENERGY'))
  assert.ok(!key.ids.has('S4'))
  assert.ok(!key.ids.has('R4'))
  assert.ok(key.edges.some(e=>e.source==='ENERGY'&&e.target==='S1'))
  assert.ok(key.edges.some(e=>e.source==='S1'&&e.target==='A'))
  assert.ok(key.edges.length<key.total_relation_count)
  const nodes=[...new Set(relations.flatMap(e=>[e.source,e.target]))].map(company_id=>({company_id}))
  assert.ok(networkHeight(nodes,key,'risk')<networkHeight(nodes,networkView(relations,'A',{direction:'both'}),'risk'))
  const second=keyRiskView(relations,'A',explanation,{order:'2',kind:'energy'})
  assert.deepEqual(new Set(second.edges.map(e=>e.relation_id)),new Set(['ENERGY-S1-energy','S1-A-supply']))
  assert.equal(JSON.stringify(explanation),snapshot)
  assert.equal(keyRiskView(relations,'A',null).edges.length,relations.length)
})

test('signed network effects distinguish mitigation and risk and rank both by magnitude',()=>{
  assert.equal(effectLabel(-.01,'一'),'一阶园区缓释')
  assert.equal(effectLabel(.01,'二'),'二阶风险传入')
  assert.equal(signedImpact(-.01),'−1.00')
  const result=filterRiskExplanation({recipients:[{company_id:'R',paths:[{order:1,relation_ids:['e'],contribution:.01,baseline_contribution:.01,delta:0,gross_contribution:.01,mitigation_contribution:0}]},{company_id:'M',paths:[{order:1,relation_ids:['e'],contribution:-.05,baseline_contribution:-.05,delta:0,gross_contribution:.02,mitigation_contribution:.07}]}]},[{relation_id:'e'}])
  assert.equal(result.recipients[0].company_id,'M')
  assert.equal(result.recipients[0].contribution,result.recipients[0].gross_contribution-result.recipients[0].mitigation_contribution)
})

test('graph morph fades old and new companies while moving the retained center continuously',()=>{
  const from={nodes:[{company_id:'A',x:420,y:270,r:36,focus:1},{company_id:'B',x:585,y:270,r:25,focus:0},{company_id:'OLD',x:50,y:50,r:22}],edges:[edge('A','B'),edge('OLD','A')]}
  const to={nodes:[{company_id:'A',x:255,y:270,r:25,focus:0},{company_id:'B',x:420,y:270,r:36,focus:1},{company_id:'NEW',x:750,y:270,r:22}],edges:[edge('A','B'),edge('B','NEW')]}
  const middle=graphTransitionFrame(from,to,.5)
  assert.equal(middle.nodes.find(n=>n.company_id==='OLD').opacity,.5)
  assert.equal(middle.nodes.find(n=>n.company_id==='NEW').opacity,.5)
  assert.equal(middle.nodes.find(n=>n.company_id==='B').x,502.5)
  assert.equal(middle.nodes.find(n=>n.company_id==='B').focus,.5)
  assert.equal(middle.nodes.find(n=>n.company_id==='A').focus,.5)
  assert.equal(middle.edges.find(e=>e.source==='OLD').opacity,.5)
  assert.equal(middle.edges.find(e=>e.target==='NEW').opacity,.5)
  assert.equal(graphTransitionFrame(from,to,1),to)
  const interrupted=graphTransitionFrame(middle,from,0)
  assert.equal(interrupted.nodes.find(n=>n.company_id==='B').x,502.5)
  assert.equal(interrupted.nodes.find(n=>n.company_id==='NEW').opacity,.5)
})

test('two-hop business view follows dependency chains, deduplicates rings and keeps filtered chains whole',()=>{
  const view=dependencyNeighborhoodView(edges,'A')
  assert.deepEqual([...view.ids].sort(),['A','B','C','M','U'])
  assert.deepEqual(view.edges.map(item=>`${item.source}->${item.target}`).sort(),['A->M','B->A','C->B','M->U'])
  assert.ok(!view.ids.has('S')) // Another customer of M is not M's own dependency.
  assert.ok(!view.ids.has('H')) // Third-hop dependency is excluded.
  const layout=networkLayout([...view.ids].map(company_id=>({company_id})),view,'A','dependency')
  assert.deepEqual(layout.find(n=>n.company_id==='A'),{company_id:'A',x:420,y:270,r:36,role:'current',dependency_depth:0})
  for(const node of layout.filter(n=>n.company_id!=='A')) {
    const depth=['B','M'].includes(node.company_id)?1:2
    assert.equal(node.dependency_depth,depth)
    const radius=((node.x-420)/(depth===1?165:330))**2+((node.y-270)/(depth===1?115:210))**2
    assert.ok(Math.abs(radius-1)<1e-10)
  }
  assert.equal(dependencyNeighborhoodView(edges,'A','energy').edges.length,4)
  const cycle=dependencyNeighborhoodView([edge('A','B'),edge('B','A'),edge('B','C'),edge('A','C')],'A')
  assert.equal(cycle.depths.get('C'),1)
  assert.equal(cycle.ids.size,3)
  assert.equal(new Set(cycle.edges.map(e=>e.relation_id)).size,cycle.edges.length)
})

test('business focus includes both direct dependency directions and replaces them when switching company',()=>{
  const view=directDependencyView(edges,'A')
  assert.deepEqual([...view.ids].sort(),['A','B','M'])
  assert.deepEqual(view.edges.map(item=>`${item.source}->${item.target}`),['A->M','B->A'])
  assert.deepEqual([...directDependencyView(edges,'A','energy').ids].sort(),['A','B'])
  assert.deepEqual([...directDependencyView(edges,'B').ids].sort(),['A','B','C','Z'])
  assert.deepEqual([...directDependencyView(edges,'ISOLATED').ids],['ISOLATED'])
  const reciprocal=directDependencyView([...edges,edge('B','A')],'A')
  assert.equal(reciprocal.ids.size,3)
  assert.equal(reciprocal.edges.length,3)
})

test('risk-source and recipient lists follow the same order and category filters',()=>{
  const first={order:1,relation_ids:['e1'],contribution:.2,baseline_contribution:.1,delta:.1}
  const second={order:2,relation_ids:['e1','e2'],contribution:.05,baseline_contribution:.02,delta:.03}
  const explanation={incoming_paths:[first,second],recipients:[{company_id:'B',paths:[first,second],risk_delta:.9}]}
  const relations=[{relation_id:'e1',dependency_class:'supply'},{relation_id:'e2',dependency_class:'energy'}]
  const result=filterRiskExplanation(explanation,relations,{order:'2',kind:'energy'})
  assert.equal(result.incoming[0].index,1)
  assert.equal(result.recipients[0].contribution,.05)
  assert.equal(result.recipients[0].delta,.03)
  assert.equal(result.recipients[0].risk_delta,.9)
  assert.equal(filterRiskExplanation(explanation,relations,{order:'1',kind:'energy'}).incoming.length,0)
})

test('dependency arrows reverse rendering while risk records remain intact',()=>{
  const raw=edge('SUPPLIER','FIRM')
  const visual=dependencyEdges([raw])[0]
  assert.equal(visual.source,'FIRM')
  assert.equal(visual.target,'SUPPLIER')
  assert.equal(visual.risk_source,'SUPPLIER')
  assert.equal(raw.source,'SUPPLIER')
})
test('combined transmission contains both directions and stable scenario-independent layout',()=>{
  const view=networkView(edges,'A',{direction:'both'})
  assert.deepEqual([...view.ids].sort(),['A','B','C','M','U'])
  assert.equal(view.roles.get('M'),'incoming')
  assert.equal(view.roles.get('C'),'outgoing')
  const nodes=[...view.ids].map(company_id=>({company_id,risk:.1}))
  const layout=networkLayout(nodes,view,'A','risk')
  assert.ok(layout.find(n=>n.company_id==='M').x<420)
  assert.ok(layout.find(n=>n.company_id==='B').x>420)
  const stressed=networkLayout(nodes.map(n=>({...n,risk:.8})),view,'A','risk')
  assert.deepEqual(layout.map(n=>[n.company_id,n.x,n.y]),stressed.map(n=>[n.company_id,n.x,n.y]))
})
test('a reciprocal subject appears once and is marked as both incoming and outgoing',()=>{
  const view=networkView([edge('A','B'),edge('B','A')],'A',{direction:'both'})
  assert.equal(view.roles.get('B'),'both')
  const layout=networkLayout([{company_id:'A'},{company_id:'B'}],view,'A','risk')
  assert.equal(layout.filter(n=>n.company_id==='B').length,1)
})

test('an incoming arrow bends around an unrelated company on its straight path',()=>{
  const a={company_id:'A',x:420,y:100,r:22,opacity:1}, f={company_id:'F',x:420,y:440,r:22,opacity:1},c={company_id:'C',x:420,y:270,r:29,opacity:1}
  assert.deepEqual(routeControlPoint(f,a,0,[a,f]),{x:420,y:270})
  const control=routeControlPoint(f,a,0,[a,f,c])
  const middleX=(f.x+2*control.x+a.x)/4
  assert.ok(Math.abs(middleX-c.x)>c.r+14)
})

test('first order shows only risk entering the selected enterprise', () => {
  const view = networkView(edges, 'A', { order: '1' })
  assert.deepEqual(view.edges.map(e => `${e.source}->${e.target}`), ['M->A'])
})
test('second order keeps both directed segments and their sequence', () => {
  const view = networkView(edges, 'A', { order: '2' })
  assert.deepEqual(view.edges.map(e => `${e.source}->${e.target}`), ['U->M', 'M->A'])
  assert.deepEqual([...view.steps.get('U-M-energy')], [1])
  assert.deepEqual([...view.steps.get('M-A-supply')], [2])
  assert.equal(view.pathCount, 1)
})
test('category filtering preserves an entire mixed-category two-hop path', () => {
  assert.equal(networkView(edges, 'A', { order: '2', kind: 'energy' }).edges.length, 2)
  assert.equal(networkView(edges, 'A', { order: '2', kind: 'infra' }).edges.length, 0)
})
test('all is exactly the union of first and second order and hides higher/unrelated nodes', () => {
  const view = networkView(edges, 'A')
  const union = new Set(['1', '2'].flatMap(order => networkView(edges, 'A', { order }).edges.map(e => e.relation_id)))
  assert.deepEqual(new Set(view.edges.map(e => e.relation_id)), union)
  assert.deepEqual([...view.ids].sort(), ['A', 'M', 'U'])
  assert.deepEqual([...view.depths], [['A', 0], ['M', 1], ['U', 2]])
})
test('second-order feedback follows the same W squared convention', () => {
  const view = networkView([edge('A', 'M'), edge('M', 'A')], 'A', { order: '2' })
  assert.equal(view.pathCount, 1)
  assert.deepEqual(view.edges.map(e => `${e.source}->${e.target}`), ['A->M', 'M->A'])
  assert.equal(view.depths.get('A'), 0)
})
test('changing selected enterprise replaces the local neighborhood', () => {
  assert.deepEqual([...networkView(edges, 'B').ids].sort(), ['A', 'B', 'M', 'Z'])
  assert.deepEqual([...networkView(edges, 'U').ids], ['U'])
})
test('initial overview retains the full park until a subject is focused', () => {
  const overview=networkView(edges,'A',{overview:true})
  assert.equal(overview.edges.length,edges.length)
  assert.ok(overview.ids.has('H'))
  assert.ok(overview.ids.has('Z'))
  assert.ok(!networkView(edges,'A').ids.has('H'))
})
test('P30 incoming diagram agrees with its TOP risk-source paths', () => {
  const park = [edge('P29','P30','infra'),edge('P25','P30','infra'),edge('P30','E')]
  const first = networkView(park,'P30',{order:'1'})
  assert.deepEqual(first.edges.map(e=>`${e.source}->${e.target}`).sort(),['P25->P30','P29->P30'])
  assert.ok(!first.ids.has('E'))
  assert.equal(networkView(park,'P30',{order:'2'}).pathCount,0)
})
test('incoming traversal does not reverse the underlying dependency arrows', () => {
  const park = [edge('D','A','energy'),edge('A','C'),edge('C','D','infra')]
  const second=networkView(park,'C',{order:'2'})
  assert.deepEqual(second.edges.map(e=>`${e.source}->${e.target}`),['D->A','A->C'])
  assert.deepEqual([...second.depths].sort(),[['A',1],['C',0],['D',2]])
  assert.equal(networkView(park,'D',{order:'1',kind:'energy'}).pathCount,0)
})

test('a large utility branch spreads second-order nodes without overlapping labels',()=>{
  const relations=[edge('HUB','A'),...Array.from({length:10},(_,i)=>edge(`SUP${i}`,'HUB'))]
  const view=dependencyNeighborhoodView(relations,'A')
  const nodes=[...view.ids].map(company_id=>({company_id}))
  const layout=networkLayout(nodes,view,'A','dependency').filter(node=>node.dependency_depth===2)
  for(let i=0;i<layout.length;i++)for(let j=i+1;j<layout.length;j++)assert.ok(Math.hypot(layout[i].x-layout[j].x,layout[i].y-layout[j].y)>90)
})
test('dense risk columns grow vertically and keep nodes inside the viewBox',()=>{
  const relations=Array.from({length:14},(_,i)=>edge(`SRC${i}`,'A'))
  const view=networkView(relations,'A',{direction:'both'})
  const nodes=[...view.ids].map(company_id=>({company_id}))
  const height=networkHeight(nodes,view,'risk')
  const layout=networkLayout(nodes,view,'A','risk')
  assert.ok(height>540)
  const sources=layout.filter(node=>node.role==='incoming').sort((a,b)=>a.y-b.y)
  sources.slice(1).forEach((node,i)=>assert.ok(node.y-sources[i].y>=64))
  assert.ok(layout.every(node=>node.y>0&&node.y<height))
})
test('typed park overview separates business roles and retains every subject',()=>{
  const roles=[...Array(12).fill('steel'),...Array(6).fill('supplier'),...Array(5).fill('customer'),...Array(7).fill('materials'),...Array(3).fill('energy'),...Array(3).fill('infra')]
  const nodes=roles.map((business_role,i)=>({company_id:`N${i}`,business_role}))
  const view={ids:new Set(nodes.map(n=>n.company_id)),edges:[]}
  const layout=networkLayout(nodes,view,'N0','dependency')
  assert.equal(layout.length,36)
  assert.equal(networkHeight(nodes,view,'dependency'),920)
  assert.ok(layout.filter(n=>n.business_role==='energy').every(n=>n.y<150))
  assert.ok(layout.filter(n=>n.business_role==='infra').every(n=>n.y>790))
  assert.ok(layout.filter(n=>n.business_role==='supplier').every(n=>n.x<200))
  assert.ok(layout.filter(n=>n.business_role==='customer').every(n=>n.x>650))
  for(let i=0;i<layout.length;i++)for(let j=i+1;j<layout.length;j++)assert.ok(Math.hypot(layout[i].x-layout[j].x,layout[i].y-layout[j].y)>=70)
})
test('routing avoids a company label even when its body is outside the straight line',()=>{
  const a={company_id:'A',x:100,y:240,r:22},b={company_id:'B',x:650,y:240,r:22},label={company_id:'LABEL',company_name:'公司名称',x:375,y:200,r:18}
  const control=routeControlPoint(a,b,0,[a,b,label])
  const middleY=(a.y+2*control.y+b.y)/4
  assert.ok(middleY>250||middleY<173)
  const parallel=routeControlPoint(a,b,24,[a,b,label])
  assert.notDeepEqual(control,parallel)
})
test('filtering risk levels and relation types reflows retained nodes and animates height',()=>{
  const relations=[edge('SUP','A','energy'),edge('UP','SUP','supply'),edge('A','DOWN','infra'),edge('DOWN','NEXT','supply')]
  const nodes=['A','SUP','UP','DOWN','NEXT'].map(company_id=>({company_id}))
  const full=networkView(relations,'A',{direction:'both'})
  const energy=networkView(relations,'A',{direction:'both',order:'1',kind:'energy'})
  const a=networkLayout(nodes,full,'A','risk'),b=networkLayout(nodes,energy,'A','risk')
  assert.equal(b.length,2)
  const from={nodes:a,edges:full.edges,height:900},to={nodes:b,edges:energy.edges,height:540}
  const middle=graphTransitionFrame(from,to,.5)
  assert.equal(middle.height,720)
  assert.equal(middle.nodes.find(n=>n.company_id==='UP').opacity,.5)
  assert.ok(middle.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)))
  assert.equal(graphTransitionFrame(from,to,1),to)
  const restarted=graphTransitionFrame(middle,from,0)
  assert.equal(restarted.height,720)
})
test('a local dependency category filter redistributes its inner and outer rings',()=>{
  const relations=[edge('SUP','A','energy'),edge('OTHER','A','supply'),edge('UP','SUP','energy'),edge('THIRD','OTHER','supply')]
  const nodes=['A','SUP','OTHER','UP','THIRD'].map(company_id=>({company_id}))
  const full=networkLayout(nodes,dependencyNeighborhoodView(relations,'A'),'A','dependency')
  const selected=networkLayout(nodes,dependencyNeighborhoodView(relations,'A','energy'),'A','dependency')
  assert.equal(selected.length,3)
  assert.notDeepEqual([full.find(n=>n.company_id==='SUP').x,full.find(n=>n.company_id==='SUP').y],[selected.find(n=>n.company_id==='SUP').x,selected.find(n=>n.company_id==='SUP').y])
})

test('fading subjects stay within the interpolated height when filtered canvas shrinks',()=>{
  const from={height:1100,nodes:[{company_id:'A',x:420,y:500,r:29},{company_id:'OLD',x:255,y:1000,r:22}],edges:[]}
  const to={height:540,nodes:[{company_id:'A',x:420,y:250,r:29},{company_id:'NEW',x:585,y:450,r:22}],edges:[]}
  for(const progress of [.1,.5,.9]){
    const frame=graphTransitionFrame(from,to,progress)
    assert.ok(frame.nodes.every(node=>node.y+node.r<frame.height))
  }
})
