<script setup>
import { computed } from "vue";
import WindowControls from "./WindowControls.vue";
import { logout, modeBadge, state } from "../state/session.js";

const stateLabel = computed(() => {
  const map = { S0: "急性缓解状态", S1: "激活状态", S2: "强化状态", S3: "维持状态" };
  return map[state.currentState] || "未评估";
});

const stateClass = computed(() =>
  state.currentState ? state.currentState.toLowerCase() : "none"
);

const isSignedIn = computed(() => state.phase !== "auth");

const profileLabel = computed(() => {
  if (!isSignedIn.value) return "未登录";
  if (state.mode === "demo") return "本地账号";
  return state.email || "已登录";
});
</script>

<template>
  <header class="bar" data-tauri-drag-region>
    <div class="brand" data-tauri-drag-region>
      <div class="name" data-tauri-drag-region>
        SitLoop
      </div>
      <span v-if="modeBadge" class="mode">{{ modeBadge }}</span>
    </div>

    <div class="side">
      <span class="pill" :class="stateClass">{{ stateLabel }}</span>

      <m3e-icon-button class="profile" variant="standard" size="small" aria-label="个人信息与账号操作">
        <m3e-menu-trigger for="profile-menu">
          <span class="material-symbols-rounded icon">account_circle</span>
        </m3e-menu-trigger>
      </m3e-icon-button>

      <WindowControls />
    </div>
  </header>

  <m3e-menu id="profile-menu">
    <m3e-menu-item disabled>
      <span slot="icon" class="material-symbols-rounded">account_circle</span>
      {{ profileLabel }}
    </m3e-menu-item>
    <m3e-menu-item v-if="isSignedIn" @click="logout">
      <span slot="icon" class="material-symbols-rounded">logout</span>
      退出
    </m3e-menu-item>
  </m3e-menu>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
  padding: 0.8rem 0.9rem 0.8rem 2.4rem;
  color: var(--md-sys-color-primary);
  user-select: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.name {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.mode {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
  font-size: 11px;
  white-space: nowrap;
}

.side {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.profile {
  --m3e-icon-button-icon-size: 24px;
  color: var(--md-sys-color-primary);
}

.icon {
  font-size: 24px;
  line-height: 1;
  display: block;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 11px;
  border-radius: 999px;
  background: var(--md-sys-color-secondary-container);
  color: var(--md-sys-color-on-secondary-container);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}


</style>
