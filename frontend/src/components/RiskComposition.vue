<script setup>
defineProps({company:{type:Object,required:true}})
import {effectLabel,signedImpact} from '../utils/riskDisplay'
const pct = value => `${(Number(value || 0)*100).toFixed(1)}%`
</script>
<template>
  <section class="risk-composition" aria-label="园区综合风险计算">
    <div class="risk-composition-equation">
      <div><span>企业自身风险</span><b>{{(Number(company.own_risk||0)*100).toFixed(1)}}%</b></div><i>＋</i>
      <div :class="company.first_order_risk<0?'risk-relief':'risk-increase'"><span>{{effectLabel(company.first_order_risk,'一')}}</span><b>{{signedImpact(company.first_order_risk,1)}}<small> 个百分点</small></b></div><i>＋</i>
      <div :class="company.second_order_risk<0?'risk-relief':'risk-increase'"><span>{{effectLabel(company.second_order_risk,'二')}}</span><b>{{signedImpact(company.second_order_risk,1)}}<small> 个百分点</small></b></div><i>＝</i>
      <div class="risk-composition-result"><span>园区综合风险</span><b>{{pct(company.network_risk)}}</b></div>
    </div>
  </section>
</template>
