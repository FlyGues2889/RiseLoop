import { ApiError } from "@sitloop/api-client";
import { SafetyShortCircuit, createLocalEngine } from "@sitloop/local-engine";

import actionsData from "../../../../data/actions/actions.json";

export const localEngine = createLocalEngine({
  storage: window.localStorage,
  library: actionsData,
});

const LOG_KEY = "sitloop.local.logs.v1";

function wrap(method) {
  return async (...args) => {
    try {
      return await method(...args);
    } catch (error) {
      if (error instanceof SafetyShortCircuit) {
        throw new ApiError(403, "safety_short_circuit", error.payload, {
          method: "POST",
          url: "local://engine",
        });
      }
      if (error.name === "LocalApiError") {
        throw new ApiError(error.status, error.payload?.detail ?? error.message, error.payload, {
          method: "POST",
          url: "local://engine",
        });
      }
      throw error;
    }
  };
}

export const localApi = {
  health: wrap(() => localEngine.health()),
  register: wrap((email, password) => localEngine.register(email, password)),
  login: wrap((email, password) => localEngine.login(email, password)),
  assessment: wrap((payload) => localEngine.assessment(payload)),
  heartbeat: wrap((payload) => localEngine.heartbeat(payload)),
  currentIntervention: wrap(() => localEngine.currentIntervention()),
  feedback: wrap((payload) => localEngine.feedback(payload)),
  askQuestion: wrap(() => localEngine.askQuestion()),
  weeklyReview: wrap(() => localEngine.weeklyReview()),
  actions: wrap((state, options) => localEngine.actions(state, options)),
};

export function loadLocalLogs() {
  try {
    const raw = window.localStorage.getItem(LOG_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveLocalLogs(logs) {
  try {
    window.localStorage.setItem(LOG_KEY, JSON.stringify(logs.slice(0, 12)));
  } catch {
    /* 存储不可用时忽略 */
  }
}

export function clearLocalLogs() {
  try {
    window.localStorage.removeItem(LOG_KEY);
  } catch {
    /* ignore */
  }
}