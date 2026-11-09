// 常驻姿势监测：摄像头生命周期、关键点采样、分钟级窗口汇总与云端上报。
// 画面只在本机处理，出网的只有 33 个归一化关键点。
import { reactive } from "vue";

import { toContractKeypoints } from "../data/keypoints.js";
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
  window: null, // { at, samples, dominant, abnormalRatio, duration }
  latest: null, // { at, posture, confidence, risk, source }
});

let landmarker = null;
let stream = null;
let video = null;
let timer = null;
let windowStart = 0;
let windowSamples = [];
let bestSample = null;

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
  if (name === "NotReadableError" || name === "AbortError") return "摄像头被其他程序占用了，关掉会议软件再试。";
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
  const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  probe.getTracks().forEach((track) => track.stop());
  await refreshDevices();
  return true;
}

async function ensureLandmarker() {
  if (landmarker) return landmarker;
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
    landmarker = await PoseLandmarker.createFromOptions(vision, options);
  } catch {
    options.baseOptions.delegate = "CPU";
    landmarker = await PoseLandmarker.createFromOptions(vision, options);
  }
  return landmarker;
}

function localPosture(landmarks) {
  const left = landmarks[11];
  const right = landmarks[12];
  const visibility = Math.min(left?.visibility ?? 0, right?.visibility ?? 0);
  if (!left || !right || visibility < 0.5) {
    return { posture: "undetermined", deviation: 0, confidence: visibility };
  }
  let degrees = (Math.atan2(right.y - left.y, right.x - left.x) * 180) / Math.PI;
  if (degrees > 90) degrees -= 180;
  if (degrees < -90) degrees += 180;
  return {
    posture: Math.abs(degrees) > 8 ? "lateral_tilt" : "baseline",
    deviation: Math.abs(degrees),
    confidence: visibility,
  };
}

function resetWindow(now) {
  windowStart = now;
  windowSamples = [];
  bestSample = null;
}

function sample() {
  if (monitor.status !== "running") return;
  const now = performance.now();

  // 窗口被系统节流打断时丢弃半截数据，不拿不完整窗口下结论
  if (monitor.lastSampleAt && now - monitor.lastSampleAt > SAMPLE_INTERVAL_MS * GAP_FACTOR) {
    monitor.gaps += 1;
    resetWindow(now);
  }
  monitor.lastSampleAt = now;

  if (!video || !landmarker || video.readyState < 2) return;
  let landmarks = null;
  try {
    landmarks = landmarker.detectForVideo(video, now)?.landmarks?.[0] ?? null;
  } catch {
    return;
  }
  monitor.points = landmarks?.length ?? 0;
  if (!landmarks || landmarks.length !== 33) return;

  const keypoints = toContractKeypoints(landmarks);
  if (!keypoints) return;

  const local = localPosture(landmarks);
  monitor.samples += 1;
  windowSamples.push({ ...local, at: now });
  if (!bestSample || local.confidence > bestSample.confidence) {
    bestSample = { ...local, keypoints };
  }

  if (now - windowStart >= WINDOW_MS) void flushWindow();
}

async function flushWindow() {
  const collected = windowSamples.slice();
  const best = bestSample;
  const startedAt = windowStart;
  resetWindow(performance.now());
  if (collected.length < 2 || !best) return;

  const determined = collected.filter((item) => item.posture !== "undetermined");
  const pool = determined.length ? determined : collected;
  const counts = {};
  for (const item of pool) counts[item.posture] = (counts[item.posture] ?? 0) + 1;
  const dominant = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
  const abnormal = determined.filter((item) => item.posture !== "baseline").length;
  const ratio = determined.length ? abnormal / determined.length : 0;
  const minutes = Math.max(0, (performance.now() - startedAt) / 60000);
  const duration = Math.round(ratio * minutes * 10) / 10;

  monitor.window = {
    at: new Date().toISOString(),
    samples: collected.length,
    dominant,
    abnormalRatio: Math.round(ratio * 100) / 100,
    duration,
  };

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
      monitor.latest = {
        at: new Date().toISOString(),
        posture: dominant,
        confidence: best.confidence,
        risk: null,
        source: "local_mode",
      };
      return;
    }
    if (!result) return;
    monitor.latest = {
      at: new Date().toISOString(),
      posture: result.posture,
      confidence: result.confidence,
      risk: result.risk,
      source: result.source,
    };
    monitor.error = "";
  } catch (err) {
    monitor.error = "这一分钟没能连上云端，稍后自动重试。";
  }
}

export async function start(deviceId = prefs.deviceId) {
  if (monitor.status === "running" || monitor.status === "starting") return;
  monitor.status = "starting";
  monitor.error = "";
  try {
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
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
    } catch (err) {
      // 设备被拔掉时退回默认摄像头
      if (deviceId && (err?.name === "OverconstrainedError" || err?.name === "NotFoundError")) {
        prefs.deviceId = null;
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 320 }, height: { ideal: 240 } },
          audio: false,
        });
      } else {
        throw err;
      }
    }

    await ensureLandmarker();
    video = document.createElement("video");
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;
    await video.play().catch(() => {});

    const track = stream.getVideoTracks()[0];
    const settings = track?.getSettings?.() ?? {};
    prefs.deviceId = settings.deviceId ?? deviceId ?? null;
    prefs.enabled = true;
    savePrefs();
    monitor.deviceId = prefs.deviceId;
    await refreshDevices();

    monitor.status = "running";
    monitor.points = 0;
    configureWindow();
    if (timer) clearInterval(timer);
    timer = setInterval(sample, SAMPLE_INTERVAL_MS);
    sample();
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
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
  if (video) {
    video.srcObject = null;
    video = null;
  }
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
