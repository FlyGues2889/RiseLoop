import { invoke } from "@tauri-apps/api/core";
import { createApiClient, ApiError, describeError } from "@riseloop/api-client";
import { computed, reactive } from "vue";

import { DEMO_UNAVAILABLE, MODES } from "../config/modes.js";
import {
  DEFAULT_PLAN_PREFERENCE,
  isPlanPreference,
  pickActionForPlan,
} from "../config/plans.js";
import { clearLocalLogs, loadLocalLogs, localApi, localEngine, saveLocalLogs } from "./local.js";

const PLAN_KEY = "riseloop.plan.v1";
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
  postureRisk: null,
  postureReport: null,
  postureEvents: loadPostureEvents(),
  lastFeedback: null,
  safety: null,
  error: null,
  log: [],
  heartbeat: null,
  ai: { question: "", answer: null, citations: [], busy: false },
  weekly: null,
  weeklyBusy: false,
  weeklyError: null,
});

export const sittingMinutes = computed(() => Math.floor(state.timer.sitting_seconds / 60));
export const modeBadge = computed(() => MODES[state.mode]?.badge ?? "");
export const aiEnabled = computed(() => MODES[state.mode]?.aiEnabled ?? true);

function pushLog(message) {
  state.log.unshift({ at: new Date().toLocaleTimeString(), message });
  state.log = state.log.slice(0, 12);
  if (state.mode === MODES.demo.id) saveLocalLogs(state.log);
}

function handleError(error) {
  if (error instanceof ApiError && error.isSafetyShortCircuit) {
    state.safety = error.payload;
    state.pending = null;
    state.pendingActions = [];
    state.error = null;
    return;
  }
  state.error = describeError(error);
}

export async function applyToken(response) {
  memoryToken = response.access_token;
  if (state.mode === MODES.cloud.id) {
    try {
      await invoke("store_session_token", { token: response.access_token });
    } catch (error) {
      pushLog("登录凭证没存进系统钥匙串，这次只在本次运行有效");
    }
  }
  state.phase = "assessment";
  state.error = null;
}

export async function restoreSession() {
  try {
    const token = await invoke("load_session_token");
    if (!token) return false;
    memoryToken = token;
    state.phase = "assessment";
    return true;
  } catch {
    return false;
  }
}

function clearToken() {
  memoryToken = null;
  return invoke("clear_session_token").catch(() => {});
}

function resetViewState() {
  state.phase = "auth";
  state.currentState = null;
  state.assessment = null;
  state.pending = null;
  state.pendingActions = [];
  state.lastFeedback = null;
  state.safety = null;
  state.error = null;
  state.heartbeat = null;
  state.weekly = null;
  state.weeklyBusy = false;
  state.weeklyError = null;
  state.ai = { question: "", answer: null, citations: [], busy: false };
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
  state.error = null;
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
        `本地模式：已恢复上次评估（${snapshot.assessment.initial_state} ${snapshot.assessment.state_name}）`
      );
    } else {
      pushLog("本地模式：全部数据保存在本机，不连接任何服务");
    }
    pushLog(`本地模式不连云端：${DEMO_UNAVAILABLE.join("、")}暂不可用`);
  } catch (error) {
    useCloud();
    state.error = describeError(error);
  } finally {
    state.busy = false;
  }
}

export async function exitDemo() {
  await clearToken();
  useCloud();
  resetViewState();
  pushLog("已回到云端模式");
}

export async function register() {
  useCloud();
  state.busy = true;
  state.error = null;
  try {
    await applyToken(await activeApi.register(state.email, state.password));
    pushLog("账号已创建，登录凭证已保存");
  } catch (error) {
    handleError(error);
  } finally {
    state.busy = false;
  }
}

export async function login() {
  useCloud();
  state.busy = true;
  state.error = null;
  try {
    await applyToken(await activeApi.login(state.email, state.password));
    pushLog("登录成功");
  } catch (error) {
    handleError(error);
  } finally {
    state.busy = false;
  }
}

export async function logout() {
  if (state.mode === MODES.demo.id) {
    await exitDemo();
    return;
  }
  await clearToken();
  resetViewState();
  pushLog("已退出，登录凭证已清除");
}

export async function submitAssessment(form) {
  state.busy = true;
  state.error = null;
  try {
    const result = await activeApi.assessment(form);
    state.assessment = result;
    state.currentState = result.initial_state;
    state.phase = "main";
    await refreshTimer();
    await startTimer();
    pushLog(`评估完成：${result.initial_state} ${result.state_name}`);
  } catch (error) {
    handleError(error);
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
    state.error = describeError(error);
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
  const reset = await timerCommand("timer_reset");
  if (reset) state.timer = reset;
  if (!state.timer.running) await startTimer();
  state.pending = null;
  state.pendingActions = [];
  if (!silent) pushLog(`久坐计时已重置（${state.timer.threshold_minutes} 分钟提醒）`);
}

export async function setThreshold(minutes) {
  const next = await timerCommand("timer_set_threshold", { minutes });
  if (next) state.timer = next;
}

export async function fastForward(minutes) {
  const next = await timerCommand("timer_seed_elapsed", { minutes });
  if (next) state.timer = next;
  pushLog(`演示：久坐计时快进到 ${minutes} 分钟`);
  await tickHeartbeat();
}

export async function tickHeartbeat() {
  if (state.phase !== "main" || state.pending || state.busy) return;
  try {
    state.heartbeat = await activeApi.heartbeat({
      sitting_minutes: sittingMinutes.value,
      threshold_minutes: state.timer.threshold_minutes,
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
      pushLog(`该起来活动了：匹配 ${actions.length} 个动作，首选「${preferred.name}」`);
    } else if (!state.heartbeat.triggered) {
      // 便于排查“点了没反应”：把云端判定写进会话记录
      pushLog(
        `还没到提醒阈值（已坐 ${sittingMinutes.value} 分钟 / 阈值 ${state.timer.threshold_minutes} 分钟）`
      );
    } else {
      pushLog("到点了，但云端没有返回可用动作");
    }
  } catch (error) {
    handleError(error);
  }
}

export async function submitFeedback(payload) {
  state.busy = true;
  state.error = null;
  try {
    const result = await activeApi.feedback(payload);
    state.lastFeedback = result;
    state.currentState = result.to_state;
    state.pending = null;
    state.pendingActions = [];
    await resetTimer({ silent: true });
    pushLog(
      `${result.from_state} → ${result.to_state}：${result.reason}`
    );
  } catch (error) {
    handleError(error);
  } finally {
    state.busy = false;
  }
}

export async function askQuestion() {
  const question = state.ai.question.trim();
  if (!aiEnabled.value || state.ai.busy || !question) return;
  state.ai.busy = true;
  state.error = null;
  try {
    const result = await activeApi.askQuestion({
      question,
      state: state.currentState,
    });
    state.ai.answer = result.answer;
    state.ai.citations = result.citations || [];
  } catch (error) {
    handleError(error);
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

export async function evaluatePostureRisk(payload) {
  if (state.mode === MODES.demo.id) return null;
  try {
    const result = await activeApi.postureRisk(payload);
    recordPostureRisk(result, payload.posture_class, payload.confidence);
    return result;
  } catch (error) {
    if (error instanceof ApiError && error.isSafetyShortCircuit) {
      handleError(error);
      return null;
    }
    return null;
  }
}

export async function evaluatePostureInfer(payload) {
  if (state.mode === MODES.demo.id) return { localMode: true };
  try {
    const result = await activeApi.postureInfer(payload);
    recordPostureRisk(result.risk, result.posture, result.confidence);
    return result;
  } catch (error) {
    if (error instanceof ApiError && error.isSafetyShortCircuit) {
      handleError(error);
      return null;
    }
    throw error;
  }
}

export function applyPostureRecommendation(result) {
  if (!result?.actions?.length) return false;
  state.pendingActions = result.actions;
  state.pending = result.actions[0];
  if (isPlanPreference(result.recommended_plan)) {
    state.planPreference = result.recommended_plan;
    savePlanPreference(result.recommended_plan);
  }
  pushLog(`姿势风险已更新，负荷 ${result.brli.toFixed(2)}，推荐动作已调整`);
  return true;
}

export function dismissSafety() {
  state.safety = null;
  state.phase = "main";
  state.pending = null;
  state.pendingActions = [];
  state.error = null;
}

export async function clearAllData() {
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