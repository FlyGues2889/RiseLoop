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
import { actionImage } from "../data/actionImages.js";

const AUTO_DISMISS_SECONDS = 15;
const TICK_MS = 200;
// .stage 上下各 0.625rem 的留白，量不到样式时用它兜底
const STAGE_PADDING = 20;
const MAX_HEIGHT = 640;
// 展开时多留一行文字的高度：下一步文字多折一行也不会再动窗口（透明窗口改尺寸会闪）
const STEP_SLACK = 26;

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
let animTimer = null;
// 展开/收起动画期间不动窗口：这时候改尺寸，透明窗口会闪一下
let animating = false;
// 上次应用的窗口高度（逻辑像素）；展开后只允许继续长高，不再往回收
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
// 示意图跟着共享会话的动作走，主窗切换动作时这里同步换图
const refImage = computed(() => actionImage(actionSession.id || action.value?.id || ""));
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

// 收起态的高度就是卡片自身高度
function collapsedHeight() {
  return Math.ceil(cardEl.value?.getBoundingClientRect().height ?? 0);
}

// 展开后的自然高度：标题 + 展开内容。收起时内容也在 DOM 里（只是被 0fr 裁掉），
// scrollHeight 已经能拿到真实高度；挂一下 .measuring 补上展开态才有的内边距。
function naturalHeight() {
  const card = cardEl.value;
  if (!card) return 0;
  const head = card.querySelector(".head");
  const inner = card.querySelector(".reveal-inner");
  if (!inner) return collapsedHeight();
  card.classList.add("measuring");
  // scrollHeight 已经含内边距，不要再加一次
  const content = inner.scrollHeight;
  card.classList.remove("measuring");
  return Math.ceil((head?.getBoundingClientRect().height ?? 0) + content);
}

// 改一次窗口就是一次重绘，透明窗口会闪；所以一次状态切换只申请一次高度
function applyHeight(cardHeight, slack = 0) {
  if (!cardHeight) return;
  const height = Math.min(MAX_HEIGHT, Math.round(cardHeight + stagePadding() + 6 + slack));
  if (Math.abs(height - appliedHeight) < 2) return;
  appliedHeight = height;
  invoke("notice_resize", { height }).catch(() => { });
}

async function fitCollapsed() {
  await nextTick();
  if (expanded.value || animating) return;
  applyHeight(collapsedHeight());
}

// 展开态内容变高（步骤文字更长、示意图加载完）才补一次高度，变矮不动窗口
async function growIfNeeded() {
  await nextTick();
  if (!expanded.value || animating) return;
  const natural = naturalHeight();
  if (!natural) return;
  const height = Math.min(MAX_HEIGHT, Math.round(natural + stagePadding() + 6 + STEP_SLACK));
  if (height > appliedHeight + 2) applyHeight(natural, STEP_SLACK);
}

// 内容一变就重新量：延迟一帧收拢同一轮变化，且只长不缩
function scheduleGrow() {
  if (resizeTimer) window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    resizeTimer = null;
    growIfNeeded();
  }, 140);
}

function playIn() {
  visible.value = false;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    visible.value = true;
  }));
}

function applyPayload(next) {
  if (!next) return;
  const wasExpanded = expanded.value;
  payload.value = next;
  action.value = next.action ?? null;
  expanded.value = false;
  appliedHeight = 0;
  remaining.value = AUTO_DISMISS_SECONDS;
  playIn();
  watchCardSize();
  // 从展开态收到新提醒时卡片要 320ms 才收回去，等动画结束再按收起高度量
  if (animTimer) window.clearTimeout(animTimer);
  animating = wasExpanded;
  animTimer = window.setTimeout(() => {
    animating = false;
    fitCollapsed();
  }, wasExpanded ? 340 : 0);
}

// 卡片尺寸会随后续内容（字体、组件内部布局、步骤文字换行）继续变，盯住它自动补量
async function watchCardSize() {
  await nextTick();
  const card = cardEl.value;
  if (!card) return;
  observer ??= new ResizeObserver(() => {
    if (expanded.value) scheduleGrow();
  });
  observer.disconnect();
  observer.observe(card);
}

function tick() {
  if (hovering.value || expanded.value || !payload.value) return;
  remaining.value -= TICK_MS / 1000;
  if (remaining.value <= 0) dismiss();
}

function expand() {
  if (expanded.value || !payload.value) return;
  // 先量好再展开：一次把窗口改到最终高度，动画期间不再碰窗口，
  // 否则「先撑到上限再收回来」会让透明窗口连闪两三下
  const natural = naturalHeight();
  expanded.value = true;
  animating = true;
  if (natural) applyHeight(natural, STEP_SLACK);
  if (animTimer) window.clearTimeout(animTimer);
  animTimer = window.setTimeout(() => {
    animating = false;
    growIfNeeded();
  }, 360);
}

function collapse() {
  if (!expanded.value) return;
  expanded.value = false;
  remaining.value = AUTO_DISMISS_SECONDS;
  // 等 grid 行高动画走完再收窗口，避免收到一半的内容又被窗口裁一次
  animating = true;
  if (animTimer) window.clearTimeout(animTimer);
  animTimer = window.setTimeout(() => {
    animating = false;
    applyHeight(collapsedHeight());
  }, 340);
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
  () => [actionSession.index, actionSession.done, actionSession.running, actionSession.loaded],
  () => {
    // 立刻量：晚一帧再改窗口，内容会先被旧的窗口高度裁一下
    if (expanded.value) growIfNeeded();
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
  document.fonts?.ready.then(() => {
    if (expanded.value) growIfNeeded();
    else fitCollapsed();
  });
  unlisteners.push(
    await listen("riseloop://notice", (event) => applyPayload(event.payload))
  );
  unlisteners.push(
    await listen("riseloop://notice-action", (event) => {
      action.value = event.payload ?? null;
      watchCardSize();
      if (expanded.value) scheduleGrow();
      else fitCollapsed();
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
  if (animTimer) window.clearTimeout(animTimer);
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
        <m3e-icon-button variant="text" aria-label="关闭" @click="dismiss">
          <span class="material-symbols-rounded">keyboard_double_arrow_down</span>
        </m3e-icon-button>
      </header>

      <div class="reveal">
        <div class="reveal-inner">
          <template v-if="action && actionSession.loaded">
            <m3e-list variant="segmented" class="run-list">
              <m3e-list-item>
                <span class="run-time">{{ timeText }}</span>
                <m3e-linear-progress-indicator v-if="!done" class="run-bar"
                  :value.prop="stepProgress"></m3e-linear-progress-indicator>
              </m3e-list-item>
              <m3e-list-item>
                <div class="run-top">
                  <img v-if="refImage" class="run-ref" :src="refImage" alt="" @load="scheduleGrow" />
                  <div class="run-copy">
                    <p class="run-step">{{ done ? "这一组做完了" : stepText }}</p>
                    <p class="run-meta">
                      {{ actionSession.name || action.name }}
                      <template v-if="!done"> · 第 {{ actionSession.index + 1 }} / {{ actionSession.steps.length }}
                        步</template>
                    </p>
                  </div>
                </div>
              </m3e-list-item>
              <m3e-list-item>
                <div class="run-actions">
                  <template v-if="!done">
                    <m3e-button v-if="!running" variant="tonal" size="small" @click="toggleAction">
                      <span slot="icon" class="material-symbols-rounded">play_arrow</span>
                      {{ fresh ? "开始" : "继续" }}
                    </m3e-button>
                    <m3e-button v-else variant="tonal" size="small" @click="toggleAction">
                      <span slot="icon" class="material-symbols-rounded">pause</span>
                      暂停
                    </m3e-button>
                    <m3e-button-group class="run-nav">
                      <m3e-icon-button variant="outlined" aria-label="上一步" :disabled.prop="actionSession.index === 0"
                        @click="retreatStep">
                        <span class="material-symbols-rounded">arrow_back</span>
                      </m3e-icon-button>
                      <m3e-icon-button variant="outlined" aria-label="下一步" @click="advanceStep">
                        <span class="material-symbols-rounded">arrow_forward</span>
                      </m3e-icon-button>
                    </m3e-button-group>
                  </template>
                </div>
              </m3e-list-item>
            </m3e-list>

            <m3e-callout v-if="action.caution" variant="surface" class="run-caution">
              <span slot="icon" class="material-symbols-rounded">info</span>
              <span slot="label">提示</span>
              {{ action.caution }}
            </m3e-callout>

            <p v-if="done" class="run-hint">做完回主界面记一下感受。</p>
          </template>

          <template v-else-if="action">
            <img v-if="refImage" class="action-ref" :src="refImage" alt="" @load="scheduleGrow" />
            <div class="action-head">
              <strong>
                {{ action.name }}<span class="tag">推荐</span>
                <m3e-chip v-if="action.desk_friendly" class="desk-tag" variant="elevated">工位可做</m3e-chip>
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
            <m3e-button variant="outlined" size="small" @click="openMain">
              <span slot="icon" class="material-symbols-rounded">open_in_new</span>
              打开主界面
            </m3e-button>
            <m3e-button v-if="!actionSession.loaded" variant="filled" size="small" @click="start">开始</m3e-button>
            <m3e-button variant="text" size="small" @click="dismiss">
              <span slot="icon" class="material-symbols-rounded">skip_next</span>
              跳过
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
        <m3e-button variant="filled" size="small" @click="expand">
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
