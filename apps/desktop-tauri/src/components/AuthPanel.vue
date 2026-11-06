<script setup>
import ErrorBanner from "./ErrorBanner.vue";
import { enterDemo, login, register, state } from "../state/session.js";
</script>

<template>
  <m3e-card variant="elevated" class="surface-card">
    <div class="surface-body">
      <header class="page-head">
        <h1>开始今天的干预</h1>
      </header>

      <form @submit.prevent="login">
        <m3e-form-field variant="filled" class="field">
          <label slot="label" for="auth-email">邮箱</label>
          <input id="auth-email" v-model="state.email" type="email" autocomplete="username" required />
        </m3e-form-field>

        <m3e-form-field variant="filled" class="field">
          <label slot="label" for="auth-password">密码</label>
          <input id="auth-password" v-model="state.password" type="password" autocomplete="current-password"
            minlength="8" placeholder="至少 8 位" required />
        </m3e-form-field>

        <ErrorBanner :error="state.error" />

        <m3e-button class="block" variant="filled" size="medium" :disabled.prop="state.busy" @click="login">
          {{ state.busy ? "登录中…" : "登录" }}
        </m3e-button>
        <m3e-button class="register" variant="text" size="small" :disabled.prop="state.busy" @click="register">
          创建账号
        </m3e-button>
      </form>

      <div class="alt">
        <span>或者进入</span>
        <m3e-button variant="text" size="small" :disabled.prop="state.busy" @click="enterDemo">
          本地演示模式
        </m3e-button>
      </div>

      <m3e-callout class="disclaimer medical-note">
        <span class="material-symbols-rounded" slot="icon">medical_information</span>
        <span slot="label">指导提示</span>
        <p>
          本产品为健康指导工具，不提供医疗诊断或治疗建议。<br>
          如出现持续疼痛、放射痛、麻木加重、肢体无力等较为严重的问题，请及时就医。
        </p>
      </m3e-callout>
    </div>
  </m3e-card>
</template>

<style scoped>
.field {
  display: block;
  margin-bottom: 1rem;
}

.block {
  width: 100%;
}

.register {
  display: block;
  margin: 10px auto 0;
}

.alt {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 18px;
  padding-top: 14px;
  color: var(--md-sys-color-secondary);
  font-size: 13px;
}
</style>
