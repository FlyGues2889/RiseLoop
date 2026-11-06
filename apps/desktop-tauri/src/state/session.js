import { invoke } from "@tauri-apps/api/core";
import { createApiClient, ApiError, describeError } from "@sitloop/api-client";
import { computed, reactive } from "vue";

import { DEMO_UNAVAILABLE, MODES } from "../config/modes.js";

let activeBaseUrl = MODES.cloud.baseUrl;
let memoryToken = null;

export const api = createApiClient({
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
});

export const sittingMinutes = computed(() => Math.floor(state.timer.sitting_seconds / 60));
export const modeBadge = computed(() => MODES[state.mode]?.badge ?? "");
export const aiEnabled = computed(() => MODES[state.mode]?.aiEnabled ?? true);

function pushLog(message) {
  state.log.unshift({ at: new Date().toLocaleTimeString(), message });
  state.log = state.log.slice(0, 12);
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
  try {
    await invoke("store_session_token", { token: response.access_token });
  } catch (error) {
    pushLog(`令牌未写入系统钥匙串，本次会话仅保存在内存：${String(error)}`);
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

function useCloud() {
  activeBaseUrl = MODES.cloud.baseUrl;
  state.mode = MODES.cloud.id;
}

function useDemo() {
  activeBaseUrl = MODES.demo.baseUrl;
  state.mode = MODES.demo.id;
}

export async function enterDemo() {
  state.busy = true;
  state.error = null;
  useDemo();
  try {
    await api.health();
    const account = MODES.demo.demoAccount;
    let response;
    try {
      response = await api.register(account.email, account.password);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        response = await api.login(account.email, account.password);
      } else {
        throw error;
      }
    }
    await applyToken(response);
    pushLog("演示模式：已连接本机数据服务，数据不出本机");
    pushLog(`演示模式不连接云端智能体：${DEMO_UNAVAILABLE.join("、")}不可用`);
  } catch (error) {
    useCloud();
    const view = describeError(error);
    if (error instanceof ApiError && error.isNetworkError) {
      view.title = "无法连接本地演示服务";
      view.message = `${MODES.demo.baseUrl} 未响应`;
      view.hint =
        "请先在项目根目录运行 pnpm demo（会自动启动 mock 模式的 cloud-api），或手动启动 apps/cloud-api 后重试。";
    } else if (error instanceof ApiError && error.status === 401) {
      view.title = "演示账号不可用";
      view.message = "本地服务拒绝了演示账号登录";
      view.hint =
        "8000 端口上可能是旧后端实例。请重启 mock 后端（SITLOOP_CLOUD_PROVIDER=mock）后重试。";
    }
    state.error = view;
  } finally {
    state.busy = false;
  }
}

export async function exitDemo() {
  await clearToken();
  useCloud();
  state.phase = "auth";
  state.currentState = null;
  state.assessment = null;
  state.pending = null;
  state.lastFeedback = null;
  pushLog("已退出演示模式，回到云端模式");
}

export async function register() {
  useCloud();
  state.busy = true;
  state.error = null;
  try {
    await applyToken(await api.register(state.email, state.password));
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
    await applyToken(await api.login(state.email, state.password));
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
  state.phase = "auth";
  state.currentState = null;
  state.assessment = null;
  state.pending = null;
  pushLog("已退出并从钥匙串清除令牌");
}

export async function submitAssessment(form) {
  state.busy = true;
  state.error = null;
  try {
    const result = await api.assessment(form);
    state.assessment = result;
    state.currentState = result.initial_state;
    state.phase = "main";
    await refreshTimer();
    await invoke("timer_start");
    pushLog(`评估完成：${result.initial_state} ${result.state_name}`);
  } catch (error) {
    handleError(error);
  } finally {
    state.busy = false;
  }
}

export async function refreshTimer() {
  state.timer = await invoke("timer_state");
}

export async function toggleTimer() {
  state.timer = state.timer.running ? await invoke("timer_pause") : await invoke("timer_start");
}

export async function resetTimer() {
  state.timer = await invoke("timer_reset");
  state.pending = null;
  state.lastFeedback = null;
  pushLog("久坐计时已重置");
}

export async function setThreshold(minutes) {
  try {
    state.timer = await invoke("timer_set_threshold", { minutes });
  } catch (error) {
    state.error = describeError(error);
  }
}

export async function fastForward(minutes) {
  state.timer = await invoke("timer_seed_elapsed", { minutes });
  pushLog(`演示：久坐计时快进到 ${minutes} 分钟`);
}

export async function tickHeartbeat() {
  if (state.phase !== "main" || state.pending || state.busy) return;
  try {
    state.heartbeat = await api.heartbeat({
      sitting_minutes: sittingMinutes.value,
      threshold_minutes: state.timer.threshold_minutes,
    });
    if (state.heartbeat.triggered && state.heartbeat.action) {
      state.pending = state.heartbeat.action;
      await invoke("timer_pause");
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
    const result = await api.feedback(payload);
    state.lastFeedback = result;
    state.currentState = result.to_state;
    state.pending = null;
    await resetTimer();
    await invoke("timer_start");
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
    const result = await api.askQuestion({
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
  if (!aiEnabled.value || state.weeklyBusy) return;
  state.weeklyBusy = true;
  state.error = null;
  try {
    state.weekly = await api.weeklyReview(7);
  } catch (error) {
    handleError(error);
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