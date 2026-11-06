<script setup>
import { computed, ref } from "vue";
import WindowControls from "./WindowControls.vue";
import { clearAllData, logout, modeBadge, state } from "../state/session.js";

const stateLabel = computed(() => {
  const map = { S0: "急性缓解状态", S1: "激活状态", S2: "强化状态", S3: "维持状态" };
  return map[state.currentState] || "未评估";
});

const isSignedIn = computed(() => state.phase !== "auth");

const profileLabel = computed(() => {
  if (!isSignedIn.value) return "未登录";
  if (state.mode === "demo") return "本地账号";
  return state.email || "已登录";
});

const confirmOpen = ref(false);
const clearing = ref(false);

async function confirmClear() {
  clearing.value = true;
  try {
    await clearAllData();
    confirmOpen.value = false;
  } finally {
    clearing.value = false;
  }
}
</script>

<template>
  <header class="bar" data-tauri-drag-region>
    <div class="brand" data-tauri-drag-region>
      <div class="name" data-tauri-drag-region>
        Rise Loop
      </div>
      <span v-if="modeBadge" class="mode">{{ modeBadge }}</span>
    </div>

    <div class="side">
      <span class="pill">{{ stateLabel }}</span>

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
    <m3e-menu-item v-if="isSignedIn" @click="confirmOpen = true">
      <span slot="icon" class="material-symbols-rounded">delete_sweep</span>
      清除数据
    </m3e-menu-item>
    <m3e-menu-item v-if="isSignedIn" @click="logout">
      <span slot="icon" class="material-symbols-rounded">logout</span>
      退出
    </m3e-menu-item>
  </m3e-menu>

  <m3e-dialog
    class="confirm"
    alert
    dismissible
    :open.prop="confirmOpen"
    @closed="confirmOpen = false"
  >
    <h2 slot="header">清除本机数据？</h2>
    <p>
      将删除本机保存的评估结果、干预记录、会话日志与登录令牌，操作不可撤销。
    </p>
    <p class="hint">
      云端账号与云端历史数据不受影响。
    </p>
    <m3e-button slot="actions" variant="text" @click="confirmOpen = false">
      取消
    </m3e-button>
    <m3e-button slot="actions" variant="filled" :disabled.prop="clearing" @click="confirmClear">
      {{ clearing ? "清除中…" : "确认清除" }}
    </m3e-button>
  </m3e-dialog>
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
  white-space: nowrap;
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

.confirm {
  --m3e-dialog-max-width: 420px;
}

.confirm .hint {
  margin-top: 8px;
}
</style>
