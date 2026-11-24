<script setup>
import { computed, ref } from "vue";
import WindowControls from "./WindowControls.vue";
import { clearAllData, logout, state } from "../state/session.js";
import { monitor, ui as cameraUi } from "../state/postureMonitor.js";

const isSignedIn = computed(() => state.phase !== "auth");
// 采集训练数据是开发工具，只在开发构建里露出，发行包不带这个入口
const showExperimental = import.meta.env.DEV;

const profileLabel = computed(() => {
  if (!isSignedIn.value) return "未登录";
  return state.email || "已登录";
});

const confirmOpen = ref(false);
const clearing = ref(false);

const trainingHint = "坐在摄像头前采集几分钟，数据存在本机";

function openTraining() {
  state.experimentalOpen = false;
  state.trainingOpen = true;
}

const monitorStatus = computed(() => {
  if (monitor.status === "running") return "监测中";
  if (monitor.status === "paused") return "已暂停";
  if (monitor.status === "starting") return "启动中";
  return "未开启";
});

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
    </div>

    <div class="side">
      <m3e-icon-button class="profile" variant="tonal" size="small" aria-label="个人信息与账号操作">
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
    <m3e-menu-item v-if="isSignedIn" @click="state.logOpen = true">
      <span slot="icon" class="material-symbols-rounded">history</span>
      会话记录
      <m3e-badge slot="trailing-icon" class="menu-count">{{ state.log.length }}</m3e-badge>
    </m3e-menu-item>
    <m3e-menu-item v-if="isSignedIn" @click="cameraUi.dialogOpen = true">
      <span slot="icon" class="material-symbols-rounded">videocam</span>
      姿势监测设置
      <span class="menu-status">{{ monitorStatus }}</span>
    </m3e-menu-item>
    <m3e-menu-item v-if="showExperimental" @click="state.experimentalOpen = true">
      <span slot="icon" class="material-symbols-rounded">science</span>
      实验性功能
    </m3e-menu-item>
    <m3e-menu-item v-if="isSignedIn" @click="confirmOpen = true">
      <span slot="icon" class="material-symbols-rounded">delete_sweep</span>
      清除本机数据
    </m3e-menu-item>
    <m3e-menu-item v-if="isSignedIn" @click="logout">
      <span slot="icon" class="material-symbols-rounded">logout</span>
      退出
    </m3e-menu-item>
  </m3e-menu>

  <m3e-dialog
    v-if="showExperimental"
    class="experimental"
    dismissible
    :open.prop="state.experimentalOpen"
    @closed="state.experimentalOpen = false"
  >
    <h2 slot="header">实验性功能</h2>
    <m3e-list variant="segmented">
      <m3e-list-item @click="openTraining">
        <span class="material-symbols-rounded" slot="leading">model_training</span>
        <div class="entry">
          <span class="entry-title">采集训练数据</span>
          <span class="entry-hint">{{ trainingHint }}</span>
        </div>
        <m3e-button slot="trailing" variant="tonal" size="small" @click.stop="openTraining">
          进入
        </m3e-button>
      </m3e-list-item>
    </m3e-list>
  </m3e-dialog>

  <m3e-dialog
    class="confirm"
    alert
    dismissible
    :open.prop="confirmOpen"
    @closed="confirmOpen = false"
  >
    <h2 slot="header">清除本机数据？</h2>
    <p>
      会删除本机的评估结果、干预记录、会话日志和登录凭证。删除后无法恢复。
    </p>
    <p class="hint">
      云端账号和历史数据不受影响。
    </p>
    <div slot="actions" end class="dialog-actions">
      <m3e-button variant="text" @click="confirmOpen = false">取消</m3e-button>
      <m3e-button variant="filled" :disabled.prop="clearing" @click="confirmClear">
        确认清除
      </m3e-button>
    </div>
  </m3e-dialog>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.75rem;
  padding: 0.8rem 0.9rem 0.8rem 2.4rem;
  color: var(--md-sys-color-primary);
  user-select: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  min-width: 0;
}

.name {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.side {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-left: auto;
}

.profile {
  --m3e-icon-button-icon-size: 1.5rem;
  /* tonal 图标按钮本身就是 secondary 容器，这里把图标色也钉在配对色上 */
  --m3e-icon-button-icon-color: var(--md-sys-color-on-secondary-container);
}

.icon {
  font-size: 1.5rem;
  line-height: 1;
  display: block;
}

.menu-status {
  margin-left: 0.5rem;
  color: var(--md-sys-color-outline);
  font-size: 0.7rem;
}

.menu-count {
  --m3e-badge-container-color: var(--md-sys-color-tertiary-container);
  --m3e-badge-color: var(--md-sys-color-on-tertiary-container);
  --m3e-badge-medium-font-size: 0.68rem;
}

.confirm {
  --m3e-dialog-max-width: 26.25rem;
}

.experimental {
  --m3e-dialog-max-width: 24rem;
}

.entry {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.entry-title {
  font-size: 0.875rem;
}

.entry-hint {
  color: var(--md-sys-color-on-surface-variant);
  font-size: 0.75rem;
}

.confirm .hint {
  margin-top: 0.5rem;
}

.dialog-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
</style>
