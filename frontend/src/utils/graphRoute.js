export function routeControlPoint(from, to, offset, nodes, height=540) {
  const [a,b] = from.company_id < to.company_id ? [from,to] : [to,from]
  const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1
  // Prefer the shortest curve that avoids both node bodies and their labels.
  const candidates=[offset,...[50,100,160,220,280].flatMap(amount=>[offset-amount,offset+amount])]
  const obstacles=nodes.filter(node=>node.company_id!==from.company_id&&node.company_id!==to.company_id&&!(node.opacity<.5)).map(node=>({...node,halfWidth:Math.max(node.r+9,Math.min(65,(node.product||node.company_name||'').length*5))}))
  let best=null,bestCost=Infinity
  for(const bend of candidates){
    const control={x:(from.x+to.x)/2-dy/length*bend,y:(from.y+to.y)/2+dx/length*bend}
    let cost=Math.abs(bend-offset)*.2,invalid=false
    const hit=new Set()
    for(let step=1;step<20;step++){
      const t=step/20,u=1-t,x=u*u*from.x+2*u*t*control.x+t*t*to.x,y=u*u*from.y+2*u*t*control.y+t*t*to.y
      if(x<12||x>828||y<12||y>height-12){invalid=true;break}
      for(const node of obstacles){
        if(x>node.x-node.halfWidth&&x<node.x+node.halfWidth&&y>node.y-node.r-9&&y<node.y+node.r+32)hit.add(node.company_id)
      }
    }
    if(invalid)continue
    cost+=hit.size*10000
    if(!hit.size&&bend===offset)return control
    if(cost<bestCost){best=control;bestCost=cost}
  }
  return best||{x:(from.x+to.x)/2,y:(from.y+to.y)/2}
}
