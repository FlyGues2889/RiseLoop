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
    <m3e-icon-button aria-label="最小化" title="最小化" @click="minimize">
      <span class="material-symbols-rounded">minimize</span>
    </m3e-icon-button>
    <m3e-icon-button aria-label="关闭" title="关闭到托盘" @click="close">
      <span class="material-symbols-rounded">close</span>
    </m3e-icon-button>
  </div>
</template>

<style scoped>
.window-controls {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: 10px;
}
</style>