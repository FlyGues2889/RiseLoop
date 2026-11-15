<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const AUTO_DISMISS_SECONDS = 15;
const TICK_MS = 200;
// .stage 上下各 0.625rem 的留白
const STAGE_PADDING = 20;
const MAX_HEIGHT = 640;

const payload = ref(null);
const action = ref(null);
const expanded = ref(false);
const hovering = ref(false);
const remaining = ref(AUTO_DISMISS_SECONDS);
const visible = ref(false);
const cardEl = ref(null);

const unlisteners = [];
let stopwatch = null;
let hideTimer = null;

function secondsLeft() {
  return Math.max(1, Math.ceil(remaining.value));
}

function progress() {
  return Math.max(0, Math.min(100, (remaining.value / AUTO_DISMISS_SECONDS) * 100));
}

function steps() {
  return (action.value?.steps ?? []).slice(0, 3);
}

async function syncHeight() {
  await nextTick();
  const card = cardEl.value;
  if (!card) return;
  const rendered = card.getBoundingClientRect().height;
  const height = Math.ceil(Math.max(rendered, card.scrollHeight)) + STAGE_PADDING + 6;
  invoke("notice_resize", { height, focusable: expanded.value }).catch(() => { });
}

function playIn() {
  visible.value = false;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    visible.value = true;
  }));
}

function applyPayload(next) {
  if (!next) return;
  payload.value = next;
  action.value = next.action ?? null;
  expanded.value = false;
  remaining.value = AUTO_DISMISS_SECONDS;
  playIn();
  syncHeight();
}

function tick() {
  if (hovering.value || expanded.value || !payload.value) return;
  remaining.value -= TICK_MS / 1000;
  if (remaining.value <= 0) dismiss();
}

async function expand() {
  if (expanded.value || !payload.value) return;
  expanded.value = true;
  // 先把窗口撑到上限（多出来是透明的），卡片在更大的画布上展开，不会被裁
  invoke("notice_resize", { height: MAX_HEIGHT, focusable: true }).catch(() => { });
  window.setTimeout(syncHeight, 360);
}

function collapse() {
  if (!expanded.value) return;
  expanded.value = false;
  remaining.value = AUTO_DISMISS_SECONDS;
  syncHeight();
  window.setTimeout(syncHeight, 340);
}

async function dismiss() {
  if (hideTimer) return;
  visible.value = false;
  remaining.value = AUTO_DISMISS_SECONDS;
  hideTimer = window.setTimeout(() => {
    hideTimer = null;
    invoke("notice_dismiss").catch(() => { });
  }, 240);
}

async function start() {
  await invoke("notice_start").catch(() => { });
}

async function openMain() {
  await invoke("notice_open_main").catch(() => { });
}

function onKeydown(event) {
  if (event.key === "Escape") {
    if (expanded.value) collapse();
    else dismiss();
  }
}

onMounted(async () => {
  try {
    applyPayload(await invoke("notice_current"));
  } catch {
    /* 单独打开页面时没有内容 */
  }
  stopwatch = window.setInterval(tick, TICK_MS);
  window.addEventListener("keydown", onKeydown);
  document.fonts?.ready.then(syncHeight);
  unlisteners.push(
    await listen("riseloop://notice", (event) => applyPayload(event.payload))
  );
  unlisteners.push(
    await listen("riseloop://notice-action", (event) => {
      action.value = event.payload ?? null;
      syncHeight();
    })
  );
  unlisteners.push(
    await listen("riseloop://notice-expand", () => {
      expand();
    })
  );
});

onBeforeUnmount(() => {
  if (stopwatch) window.clearInterval(stopwatch);
  if (hideTimer) window.clearTimeout(hideTimer);
  window.removeEventListener("keydown", onKeydown);
  unlisteners.forEach((off) => off());
});
</script>

<template>
  <div class="stage" @mouseenter="hovering = true" @mouseleave="hovering = false">
    <article
      v-if="payload"
      ref="cardEl"
      class="card"
      :class="{ expanded, visible }"
    >
      <header class="head">
        <span class="mark material-symbols-rounded">self_improvement</span>
        <div class="titles">
          <strong>{{ payload.title }}</strong>
          <small>{{ payload.body }}</small>
        </div>
        <m3e-icon-button @click="dismiss" variant="outlined">
          <span class="material-symbols-rounded">close</span>
        </m3e-icon-button>
      </header>

      <div class="reveal">
        <div class="reveal-inner">
          <template v-if="action">
            <div class="action-head">
              <strong>{{ action.name }}<span class="tag">推荐</span></strong>
              <span class="mono">{{ action.duration_minutes }} 分钟</span>
            </div>
            <ol class="steps">
              <li v-for="(step, index) in steps()" :key="index">{{ step }}</li>
            </ol>
            <p v-if="action.source" class="source">{{ action.source }}</p>
          </template>
          <p v-else class="pending">正在准备动作…</p>

          <div class="row">
            <m3e-button variant="filled" size="small" @click="start">开始</m3e-button>
            <m3e-button variant="text" size="small" @click="dismiss">稍后</m3e-button>
            <m3e-button variant="text" size="small" @click="openMain">打开主界面</m3e-button>
          </div>
        </div>
      </div>

      <footer v-if="!expanded" class="foot">
        <m3e-button variant="tonal" size="small" @click="expand">
          <span class="material-symbols-rounded" slot="icon">expand_less</span>
          看看动作
        </m3e-button>
        <span class="countdown">{{ secondsLeft() }} 秒后收起</span>
      </footer>

      <div v-if="!expanded" class="bar">
        <i :style="{ width: progress() + '%' }"></i>
      </div>
    </article>
  </div>
</template>
