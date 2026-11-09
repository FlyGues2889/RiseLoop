// MediaPipe Pose Landmarker 的 33 点顺序；必须与 cloud-api 的 MEDIAPIPE_33 保持一致。
export const MEDIAPIPE_33 = [
  "nose", "left_eye_inner", "left_eye", "left_eye_outer",
  "right_eye_inner", "right_eye", "right_eye_outer",
  "left_ear", "right_ear", "mouth_left", "mouth_right",
  "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
  "left_wrist", "right_wrist", "left_pinky", "right_pinky",
  "left_index", "right_index", "left_thumb", "right_thumb",
  "left_hip", "right_hip", "left_knee", "right_knee",
  "left_ankle", "right_ankle", "left_heel", "right_heel",
  "left_foot_index", "right_foot_index",
];

export function toContractKeypoints(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length !== MEDIAPIPE_33.length) return null;
  return landmarks.map((point, index) => ({
    name: MEDIAPIPE_33[index],
    x: round(point.x),
    y: round(point.y),
    z: round(point.z ?? 0),
    visibility: clamp01(point.visibility ?? 0),
  }));
}

function round(value) {
  return Math.round((Number(value) || 0) * 10000) / 10000;
}

function clamp01(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.min(1, Math.max(0, Math.round(number * 1000) / 1000));
}
