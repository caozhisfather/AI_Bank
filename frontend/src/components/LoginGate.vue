<script setup>
import { computed, ref } from 'vue'
import { loginSession, setAccessToken } from '../api'

const emit = defineEmits(['login'])
const role = ref('银行端')
const account = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

const roleCopy = computed(() => role.value === '银行端' ? {
  title: '银行业务端',
  subtitle: '园区组合风控与转型融资决策',
  placeholder: '客户经理工号',
  demo: '本地演示：bank_demo / demo123',
} : {
  title: '企业服务端',
  subtitle: '转型账户、项目进度与融资服务',
  placeholder: '统一社会信用代码 / 企业账号',
  demo: '本地演示：company_demo（恒岳钢铁）或 company_F（中辰建材） / demo123',
})

async function submit() {
  error.value = ''
  if (!account.value.trim() || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  busy.value = true
  try {
    const session = await loginSession({ role: role.value, account: account.value.trim(), password: password.value })
    setAccessToken(session.token)
    emit('login', session)
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-intro">
      <div class="login-brand"><span>工</span><div><b>工银·碳跃智衡</b><small>ICBC CARBON TRANSITION INTELLIGENCE</small></div></div>
      <div class="login-copy"><small>可信转型融资决策平台</small><h1>让真实转型<br>获得可信支持</h1><p>面向钢铁、建材产业园区，贯通转型真实性识别、关联风险传播、动态融资与贷后监测。</p></div>
      <ol><li><em>01</em><span>真实转型识别</span></li><li><em>02</em><span>园区链式风控</span></li><li><em>03</em><span>动态融资管理</span></li></ol>
      <footer>竞赛算法原型 · 模拟数据 · 辅助决策</footer>
    </section>
    <section class="login-panel">
      <form @submit.prevent="submit">
        <header><small>SECURE ACCESS</small><h2>{{ roleCopy.title }}</h2><p>{{ roleCopy.subtitle }}</p></header>
        <div class="role-segments"><button type="button" :class="{active:role==='银行端'}" @click="role='银行端'">银行业务端</button><button type="button" :class="{active:role==='企业端'}" @click="role='企业端'">企业服务端</button></div>
        <label><span>登录账号</span><input v-model="account" :placeholder="roleCopy.placeholder" autocomplete="username"></label>
        <label><span>登录密码</span><input v-model="password" type="password" placeholder="请输入登录密码" autocomplete="current-password"></label>
        <p v-if="error" class="login-error">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="busy">{{ busy ? '登录验证中…' : '登录并进入工作台' }} <span>→</span></button>
        <p class="demo-account">{{ roleCopy.demo }}</p>
        <div class="login-boundary">本地原型账号由后端校验并绑定角色。企业账号仅可接入和补充本企业资料，银行账号负责审核。</div>
      </form>
    </section>
  </main>
</template>
