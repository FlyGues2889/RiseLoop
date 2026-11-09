<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";

import { isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import ActivityLog from "./components/ActivityLog.vue";
import ActivityPanel from "./components/ActivityPanel.vue";
import AssessmentForm from "./components/AssessmentForm.vue";
import AuthPanel from "./components/AuthPanel.vue";
import CameraPermissionDialog from "./components/CameraPermissionDialog.vue";
import InsightPanel from "./components/InsightPanel.vue";
import InterventionCard from "./components/InterventionCard.vue";
import LoadingOverlay from "./components/LoadingOverlay.vue";
import PlanSelector from "./components/PlanSelector.vue";
import PostureSpike from "./components/PostureSpike.vue";
import SafetyAlert from "./components/SafetyAlert.vue";
import StatusBar from "./components/StatusBar.vue";
import { closePosture, refreshTimer, restoreSession, state, tickHeartbeat, tickPreview } from "./state/session.js";
import { monitor, prefs as cameraPrefs, ui as cameraUi } from "./state/postureMonitor.js";

const unlisteners = ref([]);
const heartbeatTimer = ref(null);
const previewTimer = ref(null);
const booting = ref(true);
const tauri = isTauri();

onMounted(async () => {
  try {
    await restoreSession();

    if (tauri) {
      try {
        unlisteners.value.push(
          await listen("riseloop://tick", (event) => {
            state.timer = event.payload;
          })
        );
        unlisteners.value.push(
          await listen("riseloop://threshold", () => {
            tickHeartbeat();
          })
        );
      } catch {
        /* 事件桥不可用时依赖轮询刷新 */
      }
    }

    await refreshTimer().catch(() => { });

    if (cameraPrefs.enabled) {
      monitor.resume().catch(() => { });
    } else if (state.phase === "main" && !cameraPrefs.asked) {
      cameraUi.dialogOpen = true;
    }
    heartbeatTimer.value = setInterval(() => {
      refreshTimer().catch(() => { });
      tickHeartbeat();
    }, 60_000);

    if (!tauri) {
      previewTimer.value = setInterval(tickPreview, 1000);
    }
  } finally {
    booting.value = false;
  }
});

// 每次评估完成都问一次；已经在监测中就不再打扰
function promptCamera() {
  if (cameraPrefs.enabled || monitor.status === "running") return;
  window.setTimeout(() => {
    cameraUi.dialogOpen = true;
  }, 320);
}

watch(
  () => state.phase,
  (phase, previous) => {
    if (phase === "main" && previous === "assessment") promptCamera();
    else if (phase === "main" && !cameraPrefs.asked) promptCamera();
  }
);

onUnmounted(() => {
  unlisteners.value.forEach((unlisten) => unlisten());
  if (heartbeatTimer.value) clearInterval(heartbeatTimer.value);
  if (previewTimer.value) clearInterval(previewTimer.value);
});
</script>

<template>
  <div class="app">
    <LoadingOverlay v-if="booting" fullscreen label="正在启动 Rise Loop…" />
    <StatusBar />
    <CameraPermissionDialog />
    <PostureSpike v-if="state.postureOpen" @close="closePosture" />
    <m3e-content-pane class="content">
      <div class="view" :class="`view-${state.phase}`">
        <Transition name="fade" mode="out-in">
          <AuthPanel v-if="state.phase === 'auth'" key="auth" />
          <AssessmentForm v-else-if="state.phase === 'assessment'" key="assessment" />
          <ActivityPanel v-else-if="state.pending" key="activity" />
          <InterventionCard v-else key="main" />
        </Transition>
        <div class="plan-slot" v-if="state.phase === 'main' && !state.pending">
          <PlanSelector />
        </div>
        <div class="insight-slot" v-if="state.phase === 'main' && !state.pending">
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
  position: relative;
  height: calc(100vh - 3rem);
  --m3e-content-pane-container-color: var(--md-sys-color-surface) !important;
}

.view {
  width: min(45rem, 100%);
  margin: 0 auto;
  padding: 2rem 1.5rem 2.5rem;
}

.plan-slot {
  margin-top: 1rem;
}

.insight-slot {
  margin-top: 1rem;
}
</style>
