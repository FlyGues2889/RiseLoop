<script setup>
import ErrorBanner from "./ErrorBanner.vue";
import LoadingOverlay from "./LoadingOverlay.vue";
import MedicalNote from "./MedicalNote.vue";
import { enterDemo, login, register, state } from "../state/session.js";
</script>

<template>
  <m3e-card variant="elevated" class="surface-card">
    <div class="surface-body">
      <header class="page-head">
        <h1>登录 Rise Loop</h1>
        <p class="lead">用邮箱登录，记录会同步到云端；不联网时也可以直接进入本地模式，数据只留在这台电脑上。</p>
      </header>

      <form @submit.prevent="login">
        <m3e-form-field variant="filled" class="field">
          <span class="material-symbols-rounded" slot="prefix">email</span>
          <label slot="label" for="auth-email">邮箱</label>
          <input id="auth-email" v-model="state.email" type="email" autocomplete="username" required />
        </m3e-form-field>

        <m3e-form-field variant="filled" class="field">
          <span class="material-symbols-rounded" slot="prefix">lock</span>
          <label slot="label" for="auth-password">密码</label>
          <input id="auth-password" v-model="state.password" type="password" autocomplete="current-password"
            minlength="8" placeholder="至少 8 位" required />
        </m3e-form-field>

        <ErrorBanner :error="state.error" />

        <m3e-button class="primary-action" variant="filled" :disabled.prop="state.busy" @click="login">
          {{ state.busy ? "登录中…" : "登录" }}
        </m3e-button>
        <m3e-button class="register" variant="text" size="small" :disabled.prop="state.busy" @click="register">
          创建账号
        </m3e-button>
      </form>

      <div class="alt">
        <span>或者进入</span>
        <m3e-button variant="text" size="extra-small" :disabled.prop="state.busy" @click="enterDemo">
          本地模式
        </m3e-button>
      </div>

      <MedicalNote />
    </div>
    <LoadingOverlay v-if="state.busy" label="正在登录…" />
  </m3e-card>
</template>

<style scoped>
.surface-card {
  max-width: 32rem;
}

.field {
  display: block;
  margin-bottom: 1rem;
}

/* 登录 / 创建账号：这两个是全站唯一允许的整宽按钮 */
.primary-action {
  display: block;
  width: 100%;
  margin-top: 0.75rem;
}

.register {
  display: block;
  width: 100%;
  margin: 0.5rem 0 0;
}

.alt {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  margin-top: 1.125rem;
  padding-top: 0.875rem;
  color: var(--md-sys-color-secondary);
  font-size: 0.813rem;
}
</style>
