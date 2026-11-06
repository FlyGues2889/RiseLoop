<script setup>
import { onMounted, onUnmounted, ref } from "vue";

import { listen } from "@tauri-apps/api/event";
import ActivityLog from "./components/ActivityLog.vue";
import AssessmentForm from "./components/AssessmentForm.vue";
import AuthPanel from "./components/AuthPanel.vue";
import InsightPanel from "./components/InsightPanel.vue";
import InterventionCard from "./components/InterventionCard.vue";
import SafetyAlert from "./components/SafetyAlert.vue";
import StatusBar from "./components/StatusBar.vue";
import TimeToolbar from "./components/TimeToolbar.vue";
import { refreshTimer, restoreSession, state, tickHeartbeat } from "./state/session.js";

const unlisteners = ref([]);
const heartbeatTimer = ref(null);

onMounted(async () => {
  await restoreSession();

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

  await refreshTimer().catch(() => { });
  heartbeatTimer.value = setInterval(() => {
    refreshTimer().catch(() => { });
    tickHeartbeat();
  }, 60_000);
});

onUnmounted(() => {
  unlisteners.value.forEach((unlisten) => unlisten());
  if (heartbeatTimer.value) clearInterval(heartbeatTimer.value);
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

    <Transition name="toolbar">
      <div v-if="state.phase === 'main'" class="toolbar-slot">
        <TimeToolbar />
      </div>
    </Transition>
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

.view-auth,
.view-assessment {
  padding-top: 8vh;
}

.view-main {
  padding-bottom: 118px;
}

.insight-slot {
  margin-top: 16px;
}

.toolbar-slot {
  position: fixed;
  bottom: 16px;
  left: 50%;
  z-index: 20;
  transform: translateX(-50%);
}

.toolbar-enter-from,
.toolbar-leave-to {
  opacity: 0;
  transform: translate(-50%, 12px);
}

.toolbar-enter-active,
.toolbar-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
</style>
