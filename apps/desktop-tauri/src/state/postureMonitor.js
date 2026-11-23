// 常驻姿势监测：到点才打开摄像头，采一帧、算关键点，然后立刻关掉。
// 画面只在本机处理，出网的只有 33 个归一化关键点。
import { reactive } from "vue";
import { describeError } from "@riseloop/api-client";

import { toContractKeypoints } from "../data/keypoints.js";
import { liveCameraBusy, record } from "./cameraLog.js";
import { evaluatePostureInfer, state } from "./session.js";

const PREFS_KEY = "riseloop.posture.prefs.v1";
const SAMPLE_INTERVAL_MS = 10_000;
const WINDOW_MS = 60_000;
const GAP_FACTOR = 3;

export const prefs = reactive(loadPrefs());

// 弹窗显隐由共享状态控制，菜单和启动流程都能打开它
export const ui = reactive({ dialogOpen: false });

export const monitor = reactive({
  status: "idle", // idle | starting | running | paused | error
  error: "",
  devices: [],
  deviceId: null,
  points: 0,
  samples: 0,
  gaps: 0,
  lastSampleAt: null,
  window: null, // { at, samples, posture, duration }；posture 只来自云端结果
  latest: null, // { at, posture, confidence, risk, source }
});

let landmarker = null;
let timer = null;
let sampling = false;
let windowStart = 0;
let windowSamples = [];
let bestSample = null;
let lastSkip = "";
// 姿态类别只认云端结果；这里记录云端最近一次判定，用来累计异常时长。
let confirmedPosture = null;
let confirmedSince = 0;

function loadPrefs() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}");
    return {
      asked: Boolean(parsed.asked),
      enabled: Boolean(parsed.enabled),
      deviceId: typeof parsed.deviceId === "string" ? parsed.deviceId : null,
    };
  } catch {
    return { asked: false, enabled: false, deviceId: null };
  }
}

export function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...prefs }));
  } catch {
    /* 存储不可用时只保留内存态 */
  }
}

export function cameraErrorMessage(err) {
  const name = err?.name ?? "";
  if (name === "NotAllowedError" || name === "SecurityError") return "没拿到摄像头权限，可以在系统设置里允许后重试。";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "没找到可用的摄像头。";
  if (name === "NotReadableError" || name === "AbortError") return "摄像头被其他程序占用了。";
  return "摄像头没能打开，稍后再试一次。";
}

export async function refreshDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    monitor.devices = all
      .filter((device) => device.kind === "videoinput" && device.deviceId)
      .map((device, index) => ({
        id: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`,
      }));
  } catch {
    monitor.devices = [];
  }
  return monitor.devices;
}

export async function requestPermission() {
  record("open", "申请摄像头权限", "sampling");
  try {
    const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    probe.getTracks().forEach((track) => track.stop());
    await refreshDevices();
    record("close", "权限申请完成，摄像头已关闭", "off");
    return true;
  } catch (err) {
    record("error", cameraErrorMessage(err), "off");
    throw err;
  }
}

async function buildLandmarker() {
  const { FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
  const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
  const options = {
    baseOptions: { modelAssetPath: "/models/pose_landmarker_lite.task", delegate: "GPU" },
    runningMode: "VIDEO",
    numPoses: 1,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  };
  try {
    return await PoseLandmarker.createFromOptions(vision, options);
  } catch {
    options.baseOptions.delegate = "CPU";
    return PoseLandmarker.createFromOptions(vision, options);
  }
}

async function ensureLandmarker() {
  if (!landmarker) landmarker = await buildLandmarker();
  return landmarker;
}

// 端侧只量肩线角度和可见度，不判断姿态类别；类别由云端模型给。
function measure(landmarks) {
  const left = landmarks[11];
  const right = landmarks[12];
  const visibility = Math.min(left?.visibility ?? 0, right?.visibility ?? 0);
  if (!left || !right) return { tilt: 0, visibility };
  let degrees = (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI;
  if (degrees > 90) degrees -= 180;
  if (degrees < -90) degrees += 180;
  return { tilt: Math.round(Math.abs(degrees) * 10) / 10, visibility };
}

function confirmedDuration(now) {
  if (!confirmedPosture || confirmedPosture === "baseline") return 0;
  return Math.round(((now - confirmedSince) / 60000) * 10) / 10;
}

function resetWindow(now) {
  windowStart = now;
  windowSamples = [];
  bestSample = null;
}

function ingest(landmarks, now) {
  monitor.points = landmarks?.length ?? 0;
  if (!landmarks || landmarks.length !== 33) return;

  const keypoints = toContractKeypoints(landmarks);
  if (!keypoints) return;

  const local = measure(landmarks);
  monitor.samples += 1;
  windowSamples.push({ ...local, at: now });
  if (!bestSample || local.visibility > bestSample.visibility) {
    bestSample = { ...local, keypoints };
  }

  if (now - windowStart >= WINDOW_MS) void flushWindow();
}

async function flushWindow() {
  const collected = windowSamples.slice();
  const best = bestSample;
  resetWindow(performance.now());
  if (collected.length < 2 || !best) return;

  const now = performance.now();
  const duration = confirmedDuration(now);

  const sittingMinutes = Math.floor((state.timer?.sitting_seconds ?? 0) / 60);
  try {
    const result = await evaluatePostureInfer({
      keypoints: best.keypoints,
      source: "mediapipe-pose-33",
      captured_at: new Date().toISOString(),
      posture_duration_minutes: duration,
      sitting_minutes: sittingMinutes,
      daily_sitting_minutes: sittingMinutes,
      minutes_since_last_break: sittingMinutes,
      pain_score: state.assessment?.pain_score ?? 0,
      body_parts: state.assessment?.body_parts ?? [],
      plan: state.planPreference,
    });

    if (result?.localMode) {
      // 本地模式不连云端，也就没有姿态类别可显示。
      monitor.window = {
        at: new Date().toISOString(),
        samples: collected.length,
        posture: null,
        duration: 0,
      };
      monitor.latest = null;
      monitor.error = "本地模式不连接云端，姿态由云端判定。";
      return;
    }
    if (!result) {
      monitor.window = {
        at: new Date().toISOString(),
        samples: collected.length,
        posture: null,
        duration: 0,
      };
      monitor.latest = null;
      return;
    }

    if (result.posture !== confirmedPosture) {
      confirmedPosture = result.posture;
      confirmedSince = now;
    }
    monitor.window = {
      at: new Date().toISOString(),
      samples: collected.length,
      posture: result.posture,
      duration: duration,
    };
    monitor.latest = {
      at: new Date().toISOString(),
      posture: result.posture,
      confidence: result.confidence,
      risk: result.risk,
      source: result.source,
    };
    monitor.error = "";
  } catch (err) {
    monitor.window = {
      at: new Date().toISOString(),
      samples: collected.length,
      posture: null,
      duration: 0,
    };
    monitor.latest = null;
    // 失败原因要照实说：网络断了和被云端拦下不是一回事。
    monitor.error = describeError(err).hint ?? "这一分钟没能拿到云端结果，稍后自动重试。";
  }
}

function waitFrame(el) {
  return new Promise((resolve) => {
    if (el.readyState >= 2 && el.videoWidth) return resolve();
    const done = () => {
      clearTimeout(timeout);
      resolve();
    };
    const timeout = setTimeout(done, 1500);
    el.addEventListener("loadeddata", done, { once: true });
  });
}

// 一次采样：开摄像头 → 取一帧 → 关摄像头。任何分支都必须把轨道停掉。
async function capture(deviceId) {
  const constraints = deviceId
    ? {
        deviceId: { exact: deviceId },
        width: { ideal: 320 },
        height: { ideal: 240 },
        frameRate: { ideal: 10, max: 15 },
      }
    : {
        width: { ideal: 320 },
        height: { ideal: 240 },
        frameRate: { ideal: 10, max: 15 },
        facingMode: "user",
      };

  const stream = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
  const el = document.createElement("video");
  try {
    el.autoplay = true;
    el.muted = true;
    el.playsInline = true;
    el.srcObject = stream;
    await el.play().catch(() => {});
    await waitFrame(el);

    const settings = stream.getVideoTracks()[0]?.getSettings?.() ?? {};
    let landmarks = null;
    try {
      landmarks = landmarker?.detectForVideo(el, performance.now())?.landmarks?.[0] ?? null;
    } catch {
      landmarks = null;
    }
    return { landmarks, deviceId: settings.deviceId ?? null };
  } finally {
    stream.getTracks().forEach((track) => track.stop());
    el.srcObject = null;
  }
}

async function sample() {
  if (monitor.status !== "running" || sampling) return;

  // 动作页要独占摄像头；窗口在后台也没必要开摄像头。
  // 跳过只记一次，避免日志被每 10 秒一条的重复记录刷满。
  if (liveCameraBusy()) {
    if (lastSkip !== "busy") {
      lastSkip = "busy";
      record("skip", "动作页正在用摄像头，暂停采样");
    }
    return;
  }
  if (document.hidden) {
    if (lastSkip !== "hidden") {
      lastSkip = "hidden";
      record("skip", "窗口在后台，暂停采样");
    }
    return;
  }
  try {
    await ensureLandmarker();
  } catch (err) {
    monitor.status = "error";
    monitor.error = "姿势模型没能加载，稍后再试。";
    record("error", `姿势模型加载失败（${err?.name ?? "unknown"}）`, "off");
    await release();
    return;
  }

  const before = performance.now();
  // 窗口被系统节流打断时丢弃半截数据，不拿不完整窗口下结论
  if (monitor.lastSampleAt && before - monitor.lastSampleAt > SAMPLE_INTERVAL_MS * GAP_FACTOR) {
    monitor.gaps += 1;
    resetWindow(before);
  }
  monitor.lastSampleAt = before;

  sampling = true;
  const startedAt = performance.now();
  record("open", "打开摄像头采样", "sampling");
  try {
    const { landmarks, deviceId } = await capture(prefs.deviceId);
    if (monitor.status !== "running") return;

    if (deviceId && deviceId !== prefs.deviceId) {
      prefs.deviceId = deviceId;
      monitor.deviceId = deviceId;
      savePrefs();
    }
    const now = performance.now();
    ingest(landmarks, now);
    monitor.error = "";
    lastSkip = "";
    record("close", `摄像头已关闭（${Math.round(performance.now() - startedAt)} ms）`, "off");
  } catch (err) {
    const name = err?.name ?? "";
    record("error", cameraErrorMessage(err), "off");
    // 设备被拔掉时退回默认摄像头，下次采样就能恢复
    if (name === "OverconstrainedError" || name === "NotFoundError") {
      prefs.deviceId = null;
      savePrefs();
      monitor.error = "";
    } else if (name === "NotAllowedError" || name === "SecurityError") {
      monitor.status = "error";
      monitor.error = cameraErrorMessage(err);
      await release();
    }
  } finally {
    sampling = false;
  }
}

export async function start(deviceId = prefs.deviceId) {
  if (monitor.status === "running" || monitor.status === "starting") return;
  monitor.status = "starting";
  monitor.error = "";
  try {
    await ensureLandmarker();
    await refreshDevices();

    prefs.deviceId = deviceId ?? null;
    prefs.enabled = true;
    savePrefs();
    monitor.deviceId = prefs.deviceId;

    monitor.status = "running";
    monitor.points = 0;
    configureWindow();
    if (timer) clearInterval(timer);
    timer = setInterval(sample, SAMPLE_INTERVAL_MS);
    void sample();
  } catch (err) {
    monitor.status = "error";
    monitor.error = cameraErrorMessage(err);
    await release();
    throw err;
  }
}

function configureWindow() {
  resetWindow(performance.now());
  monitor.lastSampleAt = null;
}

async function release() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  sampling = false;
  resetWindow(performance.now());
  confirmedPosture = null;
  confirmedSince = 0;
}

export async function pause() {
  if (monitor.status !== "running") return;
  await release();
  monitor.status = "paused";
  monitor.points = 0;
}

export async function resume() {
  if (monitor.status === "running" || monitor.status === "starting") return;
  return start(prefs.deviceId);
}

export async function stop() {
  await release();
  monitor.status = "idle";
  monitor.points = 0;
  prefs.enabled = false;
  savePrefs();
}

export async function switchDevice(deviceId) {
  const wasRunning = monitor.status === "running";
  await release();
  prefs.deviceId = deviceId;
  savePrefs();
  monitor.deviceId = deviceId;
  if (wasRunning) await start(deviceId);
}

export function markAsked(enabled) {
  prefs.asked = true;
  prefs.enabled = enabled;
  savePrefs();
}

/** 动作页需要独立实例：两个画面各自的视频时间戳不能混用。 */
export function createPoseLandmarker() {
  return buildLandmarker();
}
