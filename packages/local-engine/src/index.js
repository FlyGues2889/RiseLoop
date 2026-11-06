import { pickAction, selectActions, toPayload } from "./actions.js";
import { DURATION_BY_STATE, STATE_NAMES, decide, emptyCounters } from "./machine.js";
import { MEDICAL_DISCLAIMER, SafetyShortCircuit, detectInPayload } from "./safety.js";

const STORAGE_KEY = "sitloop.local.v1";
const DEFAULT_THRESHOLD_MINUTES = 45;
const COOLDOWN_MINUTES = 10;

function emptyState() {
  return {
    version: 1,
    account: null,
    assessment: null,
    session: null,
    transitions: [],
    interventions: [],
    assessments: [],
    updated_at: null,
  };
}

function initialState(payload) {
  if (payload.acute_discomfort || payload.pain_score >= 7) {
    return { state: "S0", risk: "high", intensity: "gentle" };
  }
  if (payload.pain_score >= 4) {
    return { state: "S0", risk: "medium", intensity: "gentle" };
  }
  return { state: "S1", risk: "low", intensity: "normal" };
}

function localError(status, code, payload = null) {
  const error = new Error(code);
  error.name = "LocalApiError";
  error.status = status;
  error.payload = payload;
  return error;
}

export function createLocalEngine({
  storage = globalThis.localStorage,
  library = [],
  now = () => Date.now(),
  cooldownMinutes = COOLDOWN_MINUTES,
} = {}) {
  function read() {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return emptyState();
      const parsed = JSON.parse(raw);
      return { ...emptyState(), ...parsed };
    } catch {
      return emptyState();
    }
  }

  function write(db) {
    db.updated_at = new Date(now()).toISOString();
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(db));
    } catch {
      /* 存储不可用时仅保留内存态 */
    }
    return db;
  }

  let db = read();

  function session() {
    if (db.session) return db.session;
    const fallback = db.assessment?.initial_state ?? "S1";
    return { state: fallback, counters: emptyCounters(), sitting_minutes: 0, last_push_at: null, pending_action_id: null };
  }

  function saveSession(next) {
    db.session = { ...next, updated_at: new Date(now()).toISOString() };
    write(db);
    return db.session;
  }

  function bodyParts() {
    return db.assessment?.body_parts ?? db.assessments.at(-1)?.body_parts;
  }

  function guard(payload) {
    const flags = detectInPayload(payload);
    if (flags.length > 0) throw new SafetyShortCircuit(flags);
  }

  return {
    mode: "local",

    health() {
      return Promise.resolve({ status: "ok", service: "SitLoop Local Engine", version: "1.0.0" });
    },

    register(email, password) {
      if (db.account && db.account.email === email) {
        return Promise.reject(localError(409, "email_exists", { detail: "email_exists" }));
      }
      db.account = { email };
      write(db);
      return Promise.resolve({ access_token: `local-${now()}`, token_type: "bearer", expires_in: 604800 });
    },

    login(email, password) {
      if (!db.account) {
        db.account = { email };
        write(db);
      }
      if (db.account.email !== email) {
        return Promise.reject(localError(401, "invalid_credentials", { detail: "invalid_credentials" }));
      }
      return Promise.resolve({ access_token: `local-${now()}`, token_type: "bearer", expires_in: 604800 });
    },

    async assessment(payload) {
      guard(payload);
      const { state, risk, intensity } = initialState(payload);
      const [low, high] = state === "S0" ? [2, 2] : DURATION_BY_STATE[state];
      const plan = {
        week1_goal: "建立久坐提醒与最短动作的稳定执行",
        week2_goal: "在完成率 ≥60% 的基础上延长单次干预时长",
        push_threshold_minutes: payload.available_minutes >= 10 ? 45 : 30,
        min_completions_per_week: state === "S0" ? 5 : 7,
      };
      const record = {
        assessment_id: `local-${now()}`,
        initial_state: state,
        state_name: STATE_NAMES[state],
        risk_level: risk,
        duration_range: `${low}-${high} 分钟`,
        intensity,
        plan,
        body_parts: [...payload.body_parts],
        sedentary_minutes: payload.sedentary_minutes,
        available_minutes: payload.available_minutes,
        pain_score: payload.pain_score,
        acute_discomfort: payload.acute_discomfort,
        created_at: new Date(now()).toISOString(),
      };

      db.assessment = record;
      db.assessments = [...db.assessments, record].slice(-30);
      saveSession({
        state,
        counters: emptyCounters(),
        sitting_minutes: 0,
        last_push_at: null,
        pending_action_id: null,
      });

      return Promise.resolve({ ...record, stop_exercise: false, disclaimer: MEDICAL_DISCLAIMER });
    },

    async heartbeat(payload) {
      guard(payload);
      const current = session();
      const threshold = payload.threshold_minutes || DEFAULT_THRESHOLD_MINUTES;
      const sitting = payload.sitting_minutes ?? 0;

      if (sitting < threshold) {
        return Promise.resolve({
          triggered: false,
          reason: "below_threshold",
          state: current.state,
          sitting_minutes: sitting,
          threshold_minutes: threshold,
          next_check_minutes: Math.max(1, threshold - sitting),
        });
      }

      if (current.last_push_at) {
        const elapsed = now() - new Date(current.last_push_at).getTime();
        if (elapsed < cooldownMinutes * 60 * 1000) {
          return Promise.resolve({
            triggered: false,
            reason: "cooldown",
            state: current.state,
            sitting_minutes: sitting,
            threshold_minutes: threshold,
            next_check_minutes: cooldownMinutes,
          });
        }
      }

      const action = pickAction(library, { state: current.state, bodyParts: bodyParts() });
      if (!action) {
        return Promise.resolve({
          triggered: false,
          reason: "no_action_available",
          state: current.state,
          sitting_minutes: sitting,
          threshold_minutes: threshold,
          next_check_minutes: threshold,
        });
      }

      saveSession({
        ...current,
        pending_action_id: action.id,
        last_push_at: new Date(now()).toISOString(),
        sitting_minutes: sitting,
      });

      return Promise.resolve({
        triggered: true,
        reason: "triggered",
        state: current.state,
        sitting_minutes: sitting,
        threshold_minutes: threshold,
        next_check_minutes: threshold,
        action: toPayload(action),
      });
    },

    currentIntervention() {
      const current = session();
      if (!current.pending_action_id) {
        return Promise.reject(localError(404, "no_pending_intervention", { detail: "no_pending_intervention" }));
      }
      const action = library.find((item) => item.id === current.pending_action_id);
      if (!action) {
        return Promise.reject(localError(404, "action_not_found", { detail: "action_not_found" }));
      }
      return Promise.resolve(toPayload(action));
    },

    async feedback(payload) {
      guard(payload);
      const current = session();
      const output = decide(current.state, {
        completion: payload.completion,
        feeling: payload.feeling ?? "same",
        pain_score: payload.pain_score ?? 0,
        next_day_worse: payload.next_day_worse ?? false,
        red_flags: payload.red_flags ?? [],
        obstacle: payload.obstacle ?? null,
      }, current.counters);

      if (output.transition_type !== "hold") {
        db.transitions.push({
          from_state: output.from_state,
          to_state: output.to_state,
          reason: output.reason,
          transition_type: output.transition_type,
          created_at: new Date(now()).toISOString(),
        });
      }

      db.interventions.push({
        action_id: payload.action_id,
        state: current.state,
        completion: payload.completion,
        feeling: payload.feeling ?? "same",
        pain_score: payload.pain_score ?? 0,
        obstacle: payload.obstacle ?? null,
        note: payload.note ?? "",
        pushed_at: current.last_push_at,
        created_at: new Date(now()).toISOString(),
      });

      saveSession({
        ...current,
        state: output.to_state,
        counters: output.counters,
        pending_action_id: null,
        last_push_at: null,
        sitting_minutes: 0,
      });

      const nextAction = output.stop_exercise
        ? null
        : pickAction(library, { state: output.to_state, bodyParts: bodyParts(), maxMinutes: output.duration_minutes[1] }) ??
          pickAction(library, { state: output.to_state });

      return Promise.resolve({
        from_state: output.from_state,
        to_state: output.to_state,
        transition_type: output.transition_type,
        reason: output.reason,
        duration_range: `${output.duration_minutes[0]}-${output.duration_minutes[1]} 分钟`,
        intensity: output.intensity,
        stop_exercise: output.stop_exercise,
        medical_advice: output.medical_advice,
        next_action: nextAction ? toPayload(nextAction) : null,
        disclaimer: MEDICAL_DISCLAIMER,
      });
    },

    actions(state, { bodyPart, maxMinutes } = {}) {
      const list = selectActions(library, {
        state,
        bodyParts: bodyPart ? [bodyPart] : undefined,
        maxMinutes,
      });
      return Promise.resolve(list.map(toPayload));
    },

    askQuestion() {
      return Promise.reject(localError(501, "local_mode_unavailable", { detail: "local_mode_unavailable" }));
    },

    weeklyReview() {
      return Promise.reject(localError(501, "local_mode_unavailable", { detail: "local_mode_unavailable" }));
    },

    snapshot() {
      return {
        account: db.account,
        assessment: db.assessment,
        session: db.session,
        transitions: [...db.transitions],
        interventions: [...db.interventions],
      };
    },

    hasProfile() {
      return Boolean(db.assessment);
    },

    reset() {
      db = emptyState();
      try {
        storage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    },
  };
}

export { MEDICAL_DISCLAIMER, SafetyShortCircuit, detectInPayload };