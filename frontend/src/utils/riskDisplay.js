export const effectLabel=(value,order)=>`${order}阶${Number(value)<0?'园区缓释':'风险传入'}`
export const signedImpact=(value,digits=2)=>`${Number(value)>=0?'+':'−'}${(Math.abs(Number(value||0))*100).toFixed(digits)}`
