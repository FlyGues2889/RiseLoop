<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import {
  actionSession,
  finishAction,
  initActionSession,
  nextStep as advanceStep,
  prevStep as retreatStep,
  restartAction,
  toggleAction,
} from "../state/actionSession.js";

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
let resizeTimer = null;

function secondsLeft() {
  return Math.max(1, Math.ceil(remaining.value));
}

function progress() {
  return Math.max(0, Math.min(100, (remaining.value / AUTO_DISMISS_SECONDS) * 100));
}

function steps() {
  return (action.value?.steps ?? []).slice(0, 3);
}

/* ---------- 动作卡：和主界面共用一份会话，两个窗口操作同步 ---------- */

const stepText = computed(() => actionSession.steps[actionSession.index]?.text ?? "");
const stepTotal = computed(() => actionSession.steps[actionSession.index]?.seconds ?? 0);
const stepProgress = computed(() => {
  if (stepTotal.value <= 0) return 0;
  const used = stepTotal.value - actionSession.remaining;
  return Math.max(0, Math.min(100, (used / stepTotal.value) * 100));
});
const timeText = computed(() => {
  const seconds = Math.max(0, actionSession.remaining);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return mm + ":" + ss;
});
const running = computed(() => actionSession.running);
const done = computed(() => actionSession.done);
const fresh = computed(() => actionSession.remaining >= stepTotal.value && stepTotal.value > 0);

async function syncHeight() {
  await nextTick();
  const card = cardEl.value;
  if (!card) return;
  const rendered = card.getBoundingClientRect().height;
  const height = Math.ceil(Math.max(rendered, card.scrollHeight)) + STAGE_PADDING + 6;
  invoke("notice_resize", { height, focusable: expanded.value }).catch(() => { });
}

// 内容一变就重新量高度，节流到一帧，避免每秒钟都在改窗口尺寸
function scheduleHeight() {
  if (expanded.value) invoke("notice_resize", { height: MAX_HEIGHT, focusable: true }).catch(() => { });
  if (resizeTimer) window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    resizeTimer = null;
    syncHeight();
  }, 60);
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

// 做完这一组：主窗被唤到前台并打开反馈，小窗收起
async function goFeedback() {
  await finishAction();
  visible.value = false;
}

function onKeydown(event) {
  if (event.key === "Escape") {
    if (expanded.value) collapse();
    else dismiss();
  }
}

watch(
  () => [expanded.value, actionSession.index, actionSession.done, actionSession.running, actionSession.loaded],
  () => {
    if (expanded.value) scheduleHeight();
  }
);

onMounted(async () => {
  try {
    applyPayload(await invoke("notice_current"));
  } catch {
    /* 单独打开页面时没有内容 */
  }
  await initActionSession();
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
  if (resizeTimer) window.clearTimeout(resizeTimer);
  window.removeEventListener("keydown", onKeydown);
  unlisteners.forEach((off) => off());
});
</script>

<template>
  <div class="stage" @mouseenter="hovering = true" @mouseleave="hovering = false">
    <article v-if="payload" ref="cardEl" class="card" :class="{ expanded, visible }">
      <header class="head">
        <span class="mark material-symbols-rounded">self_improvement</span>
        <div class="titles">
          <strong>{{ payload.title }}</strong>
          <small>{{ payload.body }}</small>
        </div>
        <m3e-icon-button variant="outlined" aria-label="关闭" @click="dismiss">
          <span class="material-symbols-rounded">close</span>
        </m3e-icon-button>
      </header>

      <div class="reveal">
        <div class="reveal-inner">
          <template v-if="action && actionSession.loaded">
            <p class="run-step">{{ done ? "这一组做完了" : stepText }}</p>
            <p class="run-meta">
              {{ actionSession.name || action.name }}
              <template v-if="!done"> · 第 {{ actionSession.index + 1 }} / {{ actionSession.steps.length }} 步</template>
            </p>

            <div v-if="!done" class="run-timer">
              <span class="run-time">{{ timeText }}</span>
              <span class="run-status">{{ running ? "进行中" : "已暂停" }}</span>
            </div>
            <m3e-linear-progress-indicator
              v-if="!done"
              class="run-bar"
              :value.prop="stepProgress"
            ></m3e-linear-progress-indicator>

            <div class="run-actions">
              <template v-if="done">
                <m3e-button variant="filled" size="small" @click="goFeedback">
                  <span slot="icon" class="material-symbols-rounded">edit_note</span>
                  记录感受
                </m3e-button>
                <m3e-button variant="outlined" size="small" @click="restartAction">
                  <span slot="icon" class="material-symbols-rounded">replay</span>
                  再做一次
                </m3e-button>
              </template>
              <template v-else>
                <m3e-button v-if="!running" variant="filled" size="small" @click="toggleAction">
                  <span slot="icon" class="material-symbols-rounded">play_arrow</span>
                  {{ fresh ? "开始" : "继续" }}
                </m3e-button>
                <m3e-button v-else variant="filled" size="small" @click="toggleAction">
                  <span slot="icon" class="material-symbols-rounded">pause</span>
                  暂停
                </m3e-button>
                <m3e-button-group class="run-nav">
                  <m3e-icon-button variant="outlined" aria-label="上一步"
                    :disabled.prop="actionSession.index === 0" @click="retreatStep">
                    <span class="material-symbols-rounded">arrow_back</span>
                  </m3e-icon-button>
                  <m3e-icon-button variant="outlined" aria-label="下一步" @click="advanceStep">
                    <span class="material-symbols-rounded">arrow_forward</span>
                  </m3e-icon-button>
                </m3e-button-group>
              </template>
            </div>

            <p v-if="done" class="run-hint">做完就到主界面记录一下感受吧。</p>
          </template>

          <template v-else-if="action">
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
            <m3e-button v-if="!actionSession.loaded" variant="filled" size="small" @click="start">开始</m3e-button>
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
