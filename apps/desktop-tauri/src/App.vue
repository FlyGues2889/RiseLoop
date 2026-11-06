<script setup>
import { onMounted, onUnmounted, ref } from "vue";

import { isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import ActivityLog from "./components/ActivityLog.vue";
import AssessmentForm from "./components/AssessmentForm.vue";
import AuthPanel from "./components/AuthPanel.vue";
import InsightPanel from "./components/InsightPanel.vue";
import InterventionCard from "./components/InterventionCard.vue";
import SafetyAlert from "./components/SafetyAlert.vue";
import StatusBar from "./components/StatusBar.vue";
import { refreshTimer, restoreSession, state, tickHeartbeat, tickPreview } from "./state/session.js";

const unlisteners = ref([]);
const heartbeatTimer = ref(null);
const previewTimer = ref(null);
const tauri = isTauri();

onMounted(async () => {
  await restoreSession();

  if (tauri) {
    try {
      unlisteners.value.push(
        await listen("sitloop://tick", (event) => {
          state.timer = event.payload;
        })
      );
      unlisteners.value.push(
        await listen("sitloop://threshold", () => {
          tickHeartbeat();
        })
      );
    } catch {
      /* 事件桥不可用时依赖轮询刷新 */
    }
  }

  await refreshTimer().catch(() => { });
  heartbeatTimer.value = setInterval(() => {
    refreshTimer().catch(() => { });
    tickHeartbeat();
  }, 60_000);

  if (!tauri) {
    previewTimer.value = setInterval(tickPreview, 1000);
  }
});

onUnmounted(() => {
  unlisteners.value.forEach((unlisten) => unlisten());
  if (heartbeatTimer.value) clearInterval(heartbeatTimer.value);
  if (previewTimer.value) clearInterval(previewTimer.value);
});
</script>

<template>
  <div class="app">
    <StatusBar />
    <m3e-content-pane class="content">
      <div class="view" :class="`view-${state.phase}`">
        <Transition name="fade" mode="out-in">
          <AuthPanel v-if="state.phase === 'auth'" key="auth" />
          <AssessmentForm v-else-if="state.phase === 'assessment'" key="assessment" />
          <InterventionCard v-else key="main" />
        </Transition>
        <div class="insight-slot" v-if="state.phase === 'main'">
          <InsightPanel />
        </div>
        <ActivityLog />
        <SafetyAlert />
      </div>

    </m3e-content-pane>

  </div>
</template>

<style scoped>
.app {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content {
  height: calc(100vh - 3rem);
  --m3e-content-pane-container-color: var(--md-sys-color-surface) !important;
}

.view {
  width: min(720px, 100%);
  margin: 0 auto;
  padding: 32px 24px 40px;
}

.insight-slot {
  margin-top: 16px;
}
</style>
