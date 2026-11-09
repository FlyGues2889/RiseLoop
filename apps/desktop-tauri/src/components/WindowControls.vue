<script setup>
import { isTauri } from "@tauri-apps/api/core";

const tauri = isTauri();

async function minimize() {
  if (!tauri) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().minimize();
  } catch (error) {
    console.warn("[window] minimize failed", error);
  }
}

async function close() {
  if (!tauri) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().close();
  } catch (error) {
    console.warn("[window] close failed", error);
  }
}
</script>

<template>
  <div v-if="tauri" class="window-controls">
    <m3e-icon-button id="win-minimize" aria-label="最小化" @click="minimize">
      <span class="material-symbols-rounded">minimize</span>
    </m3e-icon-button>
    <m3e-tooltip for="win-minimize">最小化</m3e-tooltip>
    <m3e-icon-button id="win-close" aria-label="关闭到托盘" @click="close">
      <span class="material-symbols-rounded">close</span>
    </m3e-icon-button>
    <m3e-tooltip for="win-close">关闭到托盘</m3e-tooltip>
  </div>
</template>

<style scoped>
.window-controls {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  margin-left: 0.625rem;
}
</style>