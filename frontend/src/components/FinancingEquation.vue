<script setup>
import { computed } from 'vue'

const props = defineProps({ decision: { type: Object, required: true } })
const amount = value => Math.round(Number(value || 0)).toLocaleString('zh-CN')
const items = computed(() => [
  { key: 'base', title: '基础授信', value: props.decision.base_limit, caption: '基于企业基本面与经营情况', operator: '+' },
  { key: 'support', title: '转型支持', value: props.decision.transition_support, caption: '结合转型目标与数据质量', operator: '−' },
  { key: 'risk', title: '风险扣减', value: props.decision.network_deduction, caption: '结合园区关联风险评估', operator: '=' },
  { key: 'result', title: '建议额度', value: props.decision.final_limit, caption: '综合转型价值与风险的授信建议' }
])
</script>

<template>
  <div class="financing-equation" role="group" aria-label="基础授信加转型支持减风险扣减，形成建议额度">
    <template v-for="item in items" :key="item.key">
      <article class="financing-amount-card" :class="`financing-amount-${item.key}`">
        <div class="financing-amount-heading">
          <span class="financing-amount-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
              <g v-if="item.key === 'base'">
                <path d="M3 21h18M5 21V7h8v14M13 11h6v10M8 4h5v3M8 10h2m-2 4h2m-2 4h2m6-4h1m-1 4h1" />
              </g>
              <g v-else-if="item.key === 'support'">
                <path d="M5 18C-1 7 11 3 21 3c0 10-4 20-14 16M4 21 16 9" />
              </g>
              <g v-else-if="item.key === 'risk'">
                <path d="m10.3 4.5-8 14A1.7 1.7 0 0 0 3.8 21h16.4a1.7 1.7 0 0 0 1.5-2.5l-8-14a2 2 0 0 0-3.4 0Z" />
                <path d="M12 9v5m0 3h.01" />
              </g>
              <g v-else>
                <ellipse cx="12" cy="5.5" rx="8" ry="3.5" />
                <path d="M4 5.5v6c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5v-6M4 11.5v6c0 2 3.6 3.5 8 3.5s8-1.5 8-3.5v-6" />
              </g>
            </svg>
          </span>
          <span class="financing-amount-label">{{ item.title }}</span>
        </div>
        <strong class="financing-amount-value">{{ amount(item.value) }}<small>万元</small></strong>
        <p class="financing-amount-caption">{{ item.caption }}</p>
      </article>
      <span v-if="item.operator" class="financing-equation-operator" aria-hidden="true">{{ item.operator }}</span>
    </template>
  </div>
</template>

<style scoped>
.financing-equation {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 20px minmax(0, 1fr) 20px minmax(0, 1fr) 20px minmax(0, 1.08fr);
  gap: 8px;
  align-items: stretch;
  margin: 24px 0 18px;
}
.financing-amount-card {
  position: relative;
  min-width: 0;
  overflow: hidden;
  padding: 18px;
  border: 1px solid #dce9e3;
  border-radius: 8px;
  background: #f7fbf9;
  box-shadow: 0 3px 12px #133e2c05;
}
.financing-amount-base { background: #f1faf7 url('../assets/base-credit-background.png') center / cover no-repeat; }
.financing-amount-support { background: linear-gradient(130deg, #fcfefd, #edf8f2); border-color: #d4e9dd; }
.financing-amount-risk { background: linear-gradient(130deg, #fffdf9, #fff4e9); border-color: #efdfca; }
.financing-amount-result { background: linear-gradient(125deg, #08644e, #003d30); border-color: #07553f; box-shadow: 0 5px 16px #0657411a; }
.financing-amount-heading { display: flex; align-items: center; gap: 10px; }
.financing-amount-icon {
  display: grid;
  place-items: center;
  flex: 0 0 34px;
  height: 34px;
  border-radius: 10px;
  color: #08745b;
  background: #deeee7;
}
.financing-amount-icon svg { width: 23px; height: 23px; }
.financing-amount-label { color: #546c61; font-size: 12px; font-weight: 500; }
.financing-amount-value {
  display: block;
  margin-top: 13px;
  color: #103e31;
  font-family: var(--font-family);
  font-size: clamp(22px, 1.9vw, 29px);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.25;
  letter-spacing: -.025em;
  white-space: nowrap;
}
.financing-amount-value small { margin-left: 5px; font-size: 13px; font-weight: 600; letter-spacing: 0; }
.financing-amount-caption { position: relative; margin: 10px 0 0; color: #768a80; font-size: 10px; line-height: 1.7; }
.financing-amount-support .financing-amount-value { color: #087453; }
.financing-amount-risk .financing-amount-icon { background: #fae9d5; color: #b86e27; }
.financing-amount-risk .financing-amount-value { color: #a85928; }
.financing-amount-result .financing-amount-icon { background: #ffffff1c; color: #e4f4e9; }
.financing-amount-result .financing-amount-label { color: #e3f1e8; }
.financing-amount-result .financing-amount-value { color: #fff3ce; }
.financing-amount-result .financing-amount-caption { color: #b6d6c7; }
.financing-amount-result::after { content: ''; position: absolute; width: 110px; height: 110px; border: 1px solid #ffffff0c; border-radius: 50%; right: -43px; top: -45px; box-shadow: 0 0 0 17px #ffffff03, 0 0 0 35px #ffffff03; pointer-events: none; }
.financing-equation-operator { display: grid; place-items: center; color: #748b80; font-size: 22px; font-weight: 400; }
@media (max-width: 1150px) {
  .financing-equation { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  .financing-equation-operator { display: none; }
  .financing-amount-support .financing-amount-value::before { content: '+ '; }
  .financing-amount-risk .financing-amount-value::before { content: '− '; }
}
@media (max-width: 560px) {
  .financing-equation { grid-template-columns: 1fr; gap: 7px; }
  .financing-amount-card { padding: 16px 18px; }
  .financing-amount-value { margin-top: 8px; font-size: 27px; }
  .financing-amount-caption { font-size: 11px; }
  .financing-equation-operator { display: grid; height: 20px; }
  .financing-amount-support .financing-amount-value::before, .financing-amount-risk .financing-amount-value::before { content: none; }
}
</style>
