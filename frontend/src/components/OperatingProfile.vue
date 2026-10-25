<script setup>
import {computed} from 'vue'
const props=defineProps({analysis:Object})
const company=computed(()=>props.analysis.company)
const history=computed(()=>props.analysis.service_history||[])
const latest=computed(()=>history.value.at(-1))
const number=v=>Number(v||0).toLocaleString('zh-CN',{maximumFractionDigits:1})
</script>
<template>
  <h2>{{company.company_name}}运行画像</h2>
  <p class="sub">{{company.product}} · {{company.process_route}}{{company.in_park?' · 园内主体':' · 园外关联主体'}}</p>
  <div class="summary-grid"><div><span>主要商品或服务</span><b>{{company.product}}</b></div><div><span>风险评价口径</span><b>运行与履约风险</b></div><div v-if="latest"><span>本期业务量</span><b>{{number(latest.quantity)}} {{latest.unit}}</b></div><div v-if="latest"><span>可用能力</span><b>{{number(latest.capacity)}} {{latest.unit}}</b></div></div>
  <p class="footnote">{{analysis.evaluation_note}}。{{company.data_source}}</p>
  <div v-if="history.length" class="table-wrap"><table><thead><tr><th>月份</th><th>商品或服务</th><th>业务量</th><th>能力上限</th><th>可用率</th></tr></thead><tbody><tr v-for="row in history.slice(-6)" :key="row.period"><td>{{row.period}}</td><td>{{row.service}}</td><td>{{number(row.quantity)}} {{row.unit}}</td><td>{{number(row.capacity)}} {{row.unit}}</td><td>{{(row.availability*100).toFixed(1)}}%</td></tr></tbody></table></div>
</template>
