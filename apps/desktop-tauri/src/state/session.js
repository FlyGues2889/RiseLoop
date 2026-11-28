import { invoke } from "@tauri-apps/api/core";
import { createApiClient, ApiError, describeError } from "@riseloop/api-client";
import { computed, reactive } from "vue";

import { DEMO_UNAVAILABLE, MODES } from "../config/modes.js";
import {
  DEFAULT_PLAN_PREFERENCE,
  isPlanPreference,
  pickActionForPlan,
} from "../config/plans.js";
import { sourceForAction } from "../data/actionSources.js";
import { clearLocalLogs, loadLocalLogs, localApi, localEngine, saveLocalLogs } from "./local.js";

// v2：默认节奏改为「快速」，旧的选择不再沿用
const PLAN_KEY = "riseloop.plan.v2";
const POSTURE_EVENTS_KEY = "riseloop.posture.events.v1";

let activeBaseUrl = MODES.cloud.baseUrl;
let memoryToken = null;

function loadPlanPreference() {
  try {
    const saved = localStorage.getItem(PLAN_KEY);
    return isPlanPreference(saved) ? saved : DEFAULT_PLAN_PREFERENCE;
  } catch {
    return DEFAULT_PLAN_PREFERENCE;
  }
}

function savePlanPreference(value) {
  try {
    localStorage.setItem(PLAN_KEY, value);
  } catch {
    /* 存储不可用时仅保留内存态 */
  }
}

function loadPostureEvents() {
  try {
    const parsed = JSON.parse(localStorage.getItem(POSTURE_EVENTS_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.slice(0, 20) : [];
  } catch {
    return [];
  }
}

function savePostureEvents(events) {
  try {
    localStorage.setItem(POSTURE_EVENTS_KEY, JSON.stringify(events.slice(0, 20)));
  } catch {
    /* 存储不可用时仅保留内存态 */
  }
}

const remoteApi = createApiClient({
  getBaseUrl: () => activeBaseUrl,
  getToken: async () => {
    if (memoryToken) return memoryToken;
    try {
      return await invoke("load_session_token");
    } catch {
      return null;
    }
  },
  // 访问令牌一小时就过期，久坐提醒一轮 45 分钟，挂后台很容易撞上过期
  onRefresh: () => refreshAccessToken(),
});

let activeApi = remoteApi;

export const state = reactive({
  phase: "auth",
  mode: MODES.cloud.id,
  planPreference: loadPlanPreference(),
  busy: false,
  email: "",
  password: "",
  assessment: null,
  currentState: null,
  timer: {
    running: false,
    sitting_seconds: 0,
    remaining_seconds: 2700,
    threshold_seconds: 2700,
    threshold_minutes: 45,
    overdue: false,
  },
  pending: null,
  pendingActions: [],
  postureOpen: false,
  logOpen: false,
  experimentalOpen: false,
  trainingOpen: false,
  postureRisk: null,
  postureReport: null,
  postureEvents: loadPostureEvents(),
  lastFeedback: null,
  safety: null,
  errors: { auth: null, assessment: null, feedback: null, qa: null, background: null },
  log: [],
  heartbeat: null,
  ai: { question: "", answer: null, citations: [], disclaimer: "", busy: false },
  weekly: null,
  weeklyBusy: false,
  weeklyError: null,
});

export const sittingMinutes = computed(() => Math.floor(state.timer.sitting_seconds / 60));
export const aiEnabled = computed(() => MODES[state.mode]?.aiEnabled ?? true);

function pushLog(message) {
  state.log.unshift({ at: new Date().toLocaleTimeString(), message });
  state.log = state.log.slice(0, 12);
  if (state.mode === MODES.demo.id) saveLocalLogs(state.log);
}

function handleError(error, scope = "background") {
  if (error instanceof ApiError && error.isSafetyShortCircuit) {
    state.safety = error.payload;
    state.pending = null;
    state.pendingActions = [];
    state.errors[scope] = null;
    return;
  }
  // 凭证真的失效时，说清原因并退回登录页，而不是留在主界面反复失败。
  if (error instanceof ApiError && error.isSessionExpired) {
    void expireSession(error);
    return;
  }
  state.errors[scope] = describeError(error);
}

async function expireSession(error) {
  const view = describeError(error);
  await clearToken();
  resetViewState();
  state.errors.auth = view;
  pushLog("登录状态已失效，请重新登录。");
}

export async function applyToken(response) {
  memoryToken = response.access_token;
  if (state.mode === MODES.cloud.id) {
    try {
      await invoke("store_session_token", { token: response.access_token });
      if (response.refresh_token) {
        await invoke("store_refresh_token", { token: response.refresh_token });
      }
    } catch (error) {
      pushLog("本次登录仅在本次运行期间有效，重启后需重新登录。");
    }
  }
  state.phase = "assessment";
  state.errors.auth = null;
}

// 用刷新令牌换一对新令牌；后端会立刻作废旧刷新令牌，所以新的那份必须存回钥匙串
async function refreshAccessToken() {
  let refreshToken = null;
  try {
    refreshToken = await invoke("load_refresh_token");
  } catch {
    return null;
  }
  if (!refreshToken) return null;
  const tokens = await remoteApi.refresh(refreshToken);
  if (!tokens?.access_token) return null;
  memoryToken = tokens.access_token;
  try {
    await invoke("store_session_token", { token: tokens.access_token });
    if (tokens.refresh_token) {
      await invoke("store_refresh_token", { token: tokens.refresh_token });
    }
  } catch {
    /* 写不进钥匙串只影响下次启动，本次运行已有的令牌仍然有效 */
  }
  return memoryToken;
}

export async function restoreSession() {
  try {
    const token = await invoke("load_session_token");
    if (!token) return false;
    memoryToken = token;
    // 钥匙串里的令牌可能已经过期，或后端换过签名密钥：先确认它还能用。
    // 否则用户会先看到评估页，填完提交时才被踢回登录。
    const review = await activeApi.weeklyReview(7);
    // 已经有评估记录的账号直接进主界面；第一次使用的才停在评估页
    if (review?.current_state) {
      state.weekly = review;
      state.currentState = review.current_state;
      state.phase = "main";
      await refreshTimer();
      return true;
    }
    state.phase = "assessment";
    return true;
  } catch (error) {
    memoryToken = null;
    if (error instanceof ApiError && error.isSessionExpired) {
      await clearToken();
      state.errors.auth = describeError(error);
    }
    return false;
  }
}

function clearToken() {
  memoryToken = null;
  return Promise.all([
    invoke("clear_session_token").catch(() => {}),
    invoke("clear_refresh_token").catch(() => {}),
  ]);
}

function resetViewState() {
  state.phase = "auth";
  state.currentState = null;
  state.assessment = null;
  state.pending = null;
  state.pendingActions = [];
  state.lastFeedback = null;
  state.safety = null;
  state.errors = { auth: null, assessment: null, feedback: null, qa: null, background: null };
  state.heartbeat = null;
  state.weekly = null;
  state.weeklyBusy = false;
  state.weeklyError = null;
  state.ai = { question: "", answer: null, citations: [], disclaimer: "", busy: false };
}

function useCloud() {
  activeBaseUrl = MODES.cloud.baseUrl;
  activeApi = remoteApi;
  state.mode = MODES.cloud.id;
}

function useDemo() {
  activeApi = localApi;
  state.mode = MODES.demo.id;
}

export async function enterDemo() {
  state.busy = true;
  state.errors.background = null;
  useDemo();
  try {
    await activeApi.health();
    const account = MODES.demo.demoAccount;
    let response;
    try {
      response = await activeApi.register(account.email, account.password);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        response = await activeApi.login(account.email, account.password);
      } else {
        throw error;
      }
    }
    await applyToken(response);

    state.log = loadLocalLogs();
    const snapshot = localEngine.snapshot();
    if (snapshot.assessment) {
      state.assessment = snapshot.assessment;
      state.currentState = snapshot.assessment.initial_state;
      state.phase = "main";
      await refreshTimer();
      await startTimer();
      pushLog(
        `本地模式：已恢复上次评估（当前阶段：${snapshot.assessment.state_name}）。`
      );
    } else {
      pushLog("本地模式：数据仅保存在本机，不连接网络。");
    }
    pushLog(`本地模式不连接云端，${DEMO_UNAVAILABLE.join("、")} 暂不可用。`);
  } catch (error) {
    useCloud();
    state.errors.background = describeError(error);
  } finally {
    state.busy = false;
  }
}

export async function exitDemo() {
  await clearToken();
  useCloud();
  resetViewState();
  pushLog("已切换回云端模式。");
}

export async function register() {
  useCloud();
  state.busy = true;
  state.errors.auth = null;
  try {
    await applyToken(await activeApi.register(state.email, state.password));
    pushLog("账号已创建，已完成登录。");
  } catch (error) {
    handleError(error, "auth");
  } finally {
    state.busy = false;
  }
}

export async function login() {
  useCloud();
  state.busy = true;
  state.errors.auth = null;
  try {
    await applyToken(await activeApi.login(state.email, state.password));
    pushLog("登录成功。");
  } catch (error) {
    handleError(error, "auth");
  } finally {
    state.busy = false;
  }
}

export async function logout() {
  if (state.mode === MODES.demo.id) {
    await exitDemo();
    return;
  }
  // 主动退出要连服务端一起吊销，否则刷新令牌还能再换一对访问令牌
  try {
    const refreshToken = await invoke("load_refresh_token");
    await remoteApi.logout(refreshToken || null);
  } catch {
    /* 断网时照样退出本机 */
  }
  await clearToken();
  resetViewState();
  pushLog("已退出登录。");
}

export async function submitAssessment(form) {
  state.busy = true;
  state.errors.assessment = null;
  try {
    const result = await activeApi.assessment(form);
    state.assessment = result;
    state.currentState = result.initial_state;
    state.phase = "main";
    await refreshTimer();
    await startTimer();
    pushLog(`评估完成，当前阶段：${result.state_name}。`);
  } catch (error) {
    handleError(error, "assessment");
  } finally {
    state.busy = false;
  }
}

const hasTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

function previewTimer(command, args) {
  const timer = state.timer;
  if (command === "timer_start") return { ...timer, running: true };
  if (command === "timer_pause") return { ...timer, running: false };
  if (command === "timer_reset") {
    return { ...timer, sitting_seconds: 0, remaining_seconds: timer.threshold_seconds, overdue: false };
  }
  if (command === "timer_restart") {
    return {
      ...timer,
      running: true,
      sitting_seconds: 0,
      remaining_seconds: timer.threshold_seconds,
      overdue: false,
    };
  }
  if (command === "timer_set_threshold") {
    const threshold = args.minutes * 60;
    return {
      ...timer,
      threshold_seconds: threshold,
      threshold_minutes: args.minutes,
      remaining_seconds: Math.max(0, threshold - timer.sitting_seconds),
      overdue: timer.sitting_seconds >= threshold,
    };
  }
  if (command === "timer_seed_elapsed") {
    const sitting = args.minutes * 60;
    return {
      ...timer,
      sitting_seconds: sitting,
      remaining_seconds: Math.max(0, timer.threshold_seconds - sitting),
      overdue: sitting >= timer.threshold_seconds,
    };
  }
  return timer;
}

async function timerCommand(command, args) {
  if (!hasTauri) return previewTimer(command, args);
  try {
    return await invoke(command, args);
  } catch (error) {
    state.errors.background = describeError(error);
    return null;
  }
}

export function tickPreview() {
  if (hasTauri || !state.timer.running || state.timer.overdue) return;
  const sitting = state.timer.sitting_seconds + 1;
  const threshold = state.timer.threshold_seconds;
  state.timer = {
    ...state.timer,
    sitting_seconds: sitting,
    remaining_seconds: Math.max(0, threshold - sitting),
    overdue: sitting >= threshold,
  };
}

/**
 * 主窗口是业务真相：算好动作后把摘要推给通知窗口，
 * 通知窗口只负责展示，不自己请求接口。
 */
async function pushNoticeAction(action) {
  if (!hasTauri || !action) return;
  const entry = sourceForAction(action.id);
  try {
    await invoke("notice_set_action", {
      minutes: sittingMinutes.value,
      action: {
        id: action.id,
        name: action.name,
        duration_minutes: action.duration_minutes ?? 0,
        steps: action.steps ?? [],
        source: entry?.title ?? null,
        caution: action.caution ?? null,
      },
    });
  } catch {
    /* 通知窗口没开时忽略 */
  }
}

async function startTimer() {
  const next = await timerCommand("timer_start");
  if (next) state.timer = next;
}

export async function refreshTimer() {
  const next = await timerCommand("timer_state");
  if (next) state.timer = next;
  return state.timer;
}

export async function toggleTimer() {
  if (state.timer.overdue) {
    await resetTimer();
    return;
  }
  if (state.timer.running) {
    const next = await timerCommand("timer_pause");
    if (next) state.timer = next;
    return;
  }
  await startTimer();
}

export async function resetTimer({ silent = false } = {}) {
  // 重置即重新开始一轮：托盘和界面共用这条路径，避免“清零了但没在走”。
  if (hasTauri) invoke("notice_dismiss").catch(() => { });
  const restarted = await timerCommand("timer_restart");
  if (restarted) state.timer = restarted;
  state.pending = null;
  state.pendingActions = [];
  if (!silent) pushLog(`久坐计时已重新开始（每 ${state.timer.threshold_minutes} 分钟提醒一次）。`);
}

export async function setThreshold(minutes) {
  const next = await timerCommand("timer_set_threshold", { minutes });
  if (next) state.timer = next;
}

export async function fastForward(minutes) {
  const next = await timerCommand("timer_seed_elapsed", { minutes });
  if (next) state.timer = next;
  pushLog(`已手动开始活动：久坐计时推进至 ${minutes} 分钟。`);
  await tickHeartbeat({ force: true });
}

export async function tickHeartbeat({ force = false } = {}) {
  if (state.phase !== "main" || state.pending || state.busy) return;
  try {
    state.heartbeat = await activeApi.heartbeat({
      sitting_minutes: sittingMinutes.value,
      threshold_minutes: state.timer.threshold_minutes,
      force,
    });
    const actions = state.heartbeat.actions?.length
      ? state.heartbeat.actions
      : state.heartbeat.action
        ? [state.heartbeat.action]
        : [];
    if (state.heartbeat.triggered && actions.length > 0) {
      const preferred = pickActionForPlan(actions, state.planPreference) ?? actions[0];
      state.pendingActions = actions;
      state.pending = preferred;
      const paused = await timerCommand("timer_pause");
      if (paused) state.timer = paused;
      await pushNoticeAction(preferred);
      pushLog(`到达提醒时间：共 ${actions.length} 个动作可选，推荐「${preferred.name}」。`);
    } else if (state.heartbeat.reason === "cooldown" && force) {
      // 手动“立即开始活动”：即使后端还在冷却期，也直接取动作让用户开始
      const fallback = await activeApi.actions(state.heartbeat.state ?? state.currentState);
      if (fallback?.length) {
        const preferred = pickActionForPlan(fallback, state.planPreference) ?? fallback[0];
        state.pendingActions = fallback.slice(0, 3);
        state.pending = preferred;
        const paused = await timerCommand("timer_pause");
        if (paused) state.timer = paused;
        await pushNoticeAction(preferred);
        pushLog(`已手动开始：共 ${state.pendingActions.length} 个动作可选，推荐「${preferred.name}」。`);
        return;
      }
      pushLog("刚刚已提醒过，暂无可执行的动作。");
    } else if (state.heartbeat.reason === "cooldown") {
      pushLog("刚刚已提醒过，10 分钟内不再重复提醒；若要立即开始活动，请点击「现在开始」按钮。");
    } else if (!state.heartbeat.triggered) {
      // 便于排查“点了没反应”：把云端判定写进会话记录
      pushLog(
        `未到提醒时间：已连续久坐 ${sittingMinutes.value} 分钟，提醒间隔 ${state.timer.threshold_minutes} 分钟。`
      );
    } else {
      pushLog("已到达提醒时间，但当前没有可用的动作。");
    }
  } catch (error) {
    handleError(error, "background");
  }
}

export async function submitFeedback(payload) {
  state.busy = true;
  state.errors.feedback = null;
  try {
    const result = await activeApi.feedback(payload);
    state.lastFeedback = result;
    state.currentState = result.to_state;
    state.pending = null;
    state.pendingActions = [];
    await resetTimer({ silent: true });
    pushLog(
      `阶段已迁移：${result.from_state} → ${result.to_state}（${result.reason}）。`
    );
  } catch (error) {
    handleError(error, "feedback");
  } finally {
    state.busy = false;
  }
}

export const advice = reactive({});

// 切页时拉一次个性化建议；模型不可用就保留页面现有文案
export async function loadAdvice(surface, fallback, context = {}) {
  if (!aiEnabled.value) return;
  try {
    const result = await activeApi.advice({
      surface,
      state: state.currentState,
      context,
      fallback,
    });
    if (result?.text && result.source === "model") advice[surface] = result.text;
  } catch {
    /* 保持现有文案 */
  }
}

export function openAssessment() {
  state.phase = "assessment";
  state.error = null;
}

export async function askQuestion() {
  const question = state.ai.question.trim();
  if (!aiEnabled.value || state.ai.busy) return;
  if (question.length < 2) {
    state.errors.qa = { title: "问题太短", message: "至少输入两个字再提问。", detail: null, hint: null };
    return;
  }
  state.ai.busy = true;
  state.errors.qa = null;
  try {
    const result = await activeApi.askQuestion({
      question,
      state: state.currentState,
    });
    state.ai.answer = result.answer;
    state.ai.citations = result.citations || [];
    state.ai.disclaimer = result.disclaimer || "";
  } catch (error) {
    handleError(error, "qa");
  } finally {
    state.ai.busy = false;
  }
}

export async function loadWeeklyReview() {
  if (state.phase !== "main" || state.weeklyBusy) return;
  state.weeklyBusy = true;
  state.weeklyError = null;
  try {
    state.weekly = await activeApi.weeklyReview(7);
  } catch (error) {
    state.weekly = null;
    state.weeklyError = describeError(error);
  } finally {
    state.weeklyBusy = false;
  }
}

export function continueAfterFeedback() {
  state.lastFeedback = null;
}

export function selectPendingAction(action) {
  if (!action) return;
  state.pending = action;
}

export function selectPlan(planId) {
  if (!isPlanPreference(planId)) return;
  state.planPreference = planId;
  savePlanPreference(planId);
  const preferred = pickActionForPlan(state.pendingActions, planId);
  if (preferred) state.pending = preferred;
}

export function openPosture() {
  state.postureOpen = true;
}

export function closePosture() {
  state.postureOpen = false;
}

export function recordPostureRisk(result, postureClass, confidence = null) {
  if (!result) return;
  const at = new Date().toISOString();
  state.postureRisk = result;
  state.postureReport = {
    posture_class: postureClass,
    confidence,
    risk_level: result.risk_level,
    brli: result.brli,
    recommended_plan: result.recommended_plan,
    citation_count: result.citations?.length ?? 0,
    updated_at: at,
  };

  if (result.risk_level !== "high" && result.risk_level !== "very_high") return;
  const last = state.postureEvents[0];
  const cooldownMs = 5 * 60 * 1000;
  if (last && new Date(at).getTime() - new Date(last.at).getTime() < cooldownMs) return;
  const events = [
    {
      at,
      posture_class: postureClass,
      risk_level: result.risk_level,
      brli: result.brli,
    },
    ...state.postureEvents,
  ].slice(0, 20);
  state.postureEvents = events;
  savePostureEvents(events);
}

export async function evaluatePostureInfer(payload) {
  if (state.mode === MODES.demo.id) return { localMode: true };
  try {
    const result = await activeApi.postureInfer(payload);
    recordPostureRisk(result.risk, result.posture, result.confidence);
    return result;
  } catch (error) {
    if (error instanceof ApiError && (error.isSafetyShortCircuit || error.isSessionExpired)) {
      // 安全短路与凭证失效都交给统一出口（后者会退回登录页）
      handleError(error, "background");
      return null;
    }
    throw error;
  }
}

export async function evaluatePostureBaseline(payload) {
  if (state.mode === MODES.demo.id) return { localMode: true };
  return activeApi.postureBaseline(payload);
}

export function applyPostureRecommendation(result) {
  if (!result?.actions?.length) return false;
  state.pendingActions = result.actions;
  state.pending = result.actions[0];
  if (isPlanPreference(result.recommended_plan)) {
    state.planPreference = result.recommended_plan;
    savePlanPreference(result.recommended_plan);
  }
  pushLog(`姿势检查结果已更新（久坐负荷 ${result.brli.toFixed(2)}），推荐动作已相应调整。`);
  return true;
}

export function dismissSafety() {
  state.safety = null;
  state.phase = "main";
  state.pending = null;
  state.pendingActions = [];
  state.errors.background = null;
}

export async function clearAllData() {
  // 先停下再清零：reset 会保留 running，直接 reset 会让计时在清空后继续走。
  await timerCommand("timer_pause");
  const reset = await timerCommand("timer_reset");
  localEngine.reset();
  clearLocalLogs();
  try {
    localStorage.removeItem(PLAN_KEY);
    localStorage.removeItem(POSTURE_EVENTS_KEY);
  } catch {
    /* 存储不可用时忽略 */
  }
  state.planPreference = DEFAULT_PLAN_PREFERENCE;
  state.postureRisk = null;
  state.postureReport = null;
  state.postureEvents = [];
  await clearToken();
  useCloud();
  resetViewState();
  state.email = "";
  state.password = "";
  state.log = [];
  state.busy = false;
  state.timer = reset
    ? { ...reset, running: false }
    : {
        running: false,
        sitting_seconds: 0,
        remaining_seconds: 2700,
        threshold_seconds: 2700,
        threshold_minutes: 45,
        overdue: false,
      };
}
export function clearError(scope) {
  if (state.errors[scope] !== undefined) state.errors[scope] = null;
}
