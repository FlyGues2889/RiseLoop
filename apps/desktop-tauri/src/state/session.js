import { invoke } from "@tauri-apps/api/core";
import { createApiClient, ApiError, describeError } from "@sitloop/api-client";
import { computed, reactive } from "vue";

import { DEMO_UNAVAILABLE, MODES } from "../config/modes.js";
import { clearLocalLogs, loadLocalLogs, localApi, localEngine, saveLocalLogs } from "./local.js";

let activeBaseUrl = MODES.cloud.baseUrl;
let memoryToken = null;

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
      pushLog(`令牌未写入系统钥匙串，本次会话仅保存在内存：${String(error)}`);
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
    pushLog(`本地模式不连接云端智能体：${DEMO_UNAVAILABLE.join("、")}不可用`);
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
  pushLog("已退出本地模式，回到云端模式");
}

export async function register() {
  useCloud();
  state.busy = true;
  state.error = null;
  try {
    await applyToken(await activeApi.register(state.email, state.password));
    pushLog("账号已创建，令牌已写入系统钥匙串");
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
  pushLog("已退出并从钥匙串清除令牌");
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
    if (state.heartbeat.triggered && state.heartbeat.action) {
      state.pending = state.heartbeat.action;
      const paused = await timerCommand("timer_pause");
      if (paused) state.timer = paused;
      pushLog(`触发干预：${state.heartbeat.action.name}`);
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
    await resetTimer({ silent: true });
    pushLog(
      `${result.from_state} → ${result.to_state}（${result.transition_type}）${result.reason}`
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

export function dismissSafety() {
  state.safety = null;
  state.phase = "main";
  state.pending = null;
  state.error = null;
}

export async function clearAllData() {
  const reset = await timerCommand("timer_reset");
  localEngine.reset();
  clearLocalLogs();
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