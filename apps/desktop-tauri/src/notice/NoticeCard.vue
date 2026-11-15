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
// .stage 上下各 0.625rem 的留白，量不到样式时用它兜底
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
// 上次应用的窗口高度（逻辑像素），没变就不动窗口，避免点按钮时闪
let appliedHeight = 0;
let observer = null;

function secondsLeft() {
  return Math.max(1, Math.ceil(remaining.value));
}

function progress() {
  return Math.max(0, Math.min(100, (remaining.value / AUTO_DISMISS_SECONDS) * 100));
}

function steps() {
  // 步骤里已经不含「重复 N 轮」这种概括写法，全部列出来才看得懂
  return action.value?.steps ?? [];
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

function stagePadding() {
  const stage = cardEl.value?.closest(".stage");
  if (!stage) return STAGE_PADDING;
  const style = window.getComputedStyle(stage);
  const top = Number.parseFloat(style.paddingTop) || 0;
  const bottom = Number.parseFloat(style.paddingBottom) || 0;
  return top + bottom;
}

// 卡片自然高度。展开态可能被窗口高度卡住（内容在内部滚动），
// 这时卡片自身的 rect 只是可见高度，要按「标题 + 内容自然高度」重算，否则窗口永远差一截。
function cardHeight() {
  const card = cardEl.value;
  if (!card) return 0;
  const rect = card.getBoundingClientRect().height;
  if (!expanded.value) return Math.ceil(rect);
  const head = card.querySelector(".head");
  const inner = card.querySelector(".reveal-inner");
  const natural =
    (head?.getBoundingClientRect().height ?? 0) + (inner?.scrollHeight ?? 0);
  return Math.ceil(Math.max(rect, natural));
}

async function syncHeight(force = false) {
  await nextTick();
  const measured = cardHeight();
  if (!measured) return;
  const height = Math.min(MAX_HEIGHT, Math.round(measured + stagePadding() + 6));
  if (!force && Math.abs(height - appliedHeight) < 2) return;
  appliedHeight = height;
  invoke("notice_resize", { height, focusable: expanded.value }).catch(() => { });
}

// 内容一变就重新量高度：延迟一帧收拢同一轮变化，高度没变时不会真的去动窗口
function scheduleHeight(force = false) {
  if (resizeTimer) window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    resizeTimer = null;
    syncHeight(force);
  }, 80);
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
  appliedHeight = 0;
  remaining.value = AUTO_DISMISS_SECONDS;
  playIn();
  watchCardSize();
  syncHeight(true);
}

// 卡片尺寸会随后续内容（字体、组件内部布局、步骤文字换行）继续变，盯住它自动补量
async function watchCardSize() {
  await nextTick();
  const card = cardEl.value;
  if (!card) return;
  observer ??= new ResizeObserver(() => {
    if (expanded.value) scheduleHeight();
  });
  observer.disconnect();
  observer.observe(card);
}

function tick() {
  if (hovering.value || expanded.value || !payload.value) return;
  remaining.value -= TICK_MS / 1000;
  if (remaining.value <= 0) dismiss();
}

async function expand() {
  if (expanded.value || !payload.value) return;
  expanded.value = true;
  // 先把窗口撑到上限（多出来是透明的，看不见），让卡片在不受限的画布里先摊开，
  // 之后再按真实内容收回到刚好够用，避免「先按被裁的高度量，量出来永远偏小」
  invoke("notice_resize", { height: MAX_HEIGHT, focusable: true }).catch(() => { });
  window.setTimeout(() => syncHeight(true), 340);
  window.setTimeout(() => syncHeight(true), 700);
}

function collapse() {
  if (!expanded.value) return;
  expanded.value = false;
  remaining.value = AUTO_DISMISS_SECONDS;
  window.setTimeout(() => syncHeight(true), 60);
  window.setTimeout(() => syncHeight(true), 380);
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
  document.fonts?.ready.then(() => scheduleHeight(true));
  unlisteners.push(
    await listen("riseloop://notice", (event) => applyPayload(event.payload))
  );
  unlisteners.push(
    await listen("riseloop://notice-action", (event) => {
      action.value = event.payload ?? null;
      watchCardSize();
      syncHeight(true);
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
  observer?.disconnect();
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
                <m3e-button v-if="!running" variant="tonal" size="small" @click="toggleAction">
                  <span slot="icon" class="material-symbols-rounded">play_arrow</span>
                  {{ fresh ? "开始" : "继续" }}
                </m3e-button>
                <m3e-button v-else variant="tonal" size="small" @click="toggleAction">
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

            <m3e-callout v-if="action.caution" variant="surface" class="run-caution">
              <span slot="icon" class="material-symbols-rounded">info</span>
              <span slot="label">提示</span>
              {{ action.caution }}
            </m3e-callout>

            <p v-if="done" class="run-hint">做完就到主界面记录一下感受吧。</p>
          </template>

          <template v-else-if="action">
            <div class="action-head">
              <strong>
                {{ action.name }}<span class="tag">推荐</span>
                <m3e-chip v-if="action.desk_friendly" class="desk-tag">工位可做</m3e-chip>
              </strong>
              <span class="mono">{{ action.duration_minutes }} 分钟</span>
            </div>
            <m3e-list class="steps">
              <m3e-list-item v-for="(step, index) in steps()" :key="index">
                <span slot="leading" class="step-no">{{ index + 1 }}</span>
                {{ step }}
              </m3e-list-item>
            </m3e-list>
            <p v-if="action.source" class="source">{{ action.source }}</p>
          </template>
          <p v-else class="pending">正在准备动作…</p>

          <div class="row">
            <m3e-button v-if="!actionSession.loaded" variant="filled" size="small" @click="start">开始</m3e-button>
            <m3e-button variant="text" size="small" @click="dismiss">
              <span slot="icon" class="material-symbols-rounded">skip_next</span>
              跳过
            </m3e-button>
            <m3e-button variant="text" size="small" @click="openMain">
              <span slot="icon" class="material-symbols-rounded">open_in_new</span>
              打开主界面
            </m3e-button>
          </div>

          <m3e-callout v-if="action && action.caution && !actionSession.loaded" variant="surface" class="run-caution">
            <span slot="icon" class="material-symbols-rounded">info</span>
            <span slot="label">提示</span>
            {{ action.caution }}
          </m3e-callout>
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
