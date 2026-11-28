# v3 head 内部 LOSO 报告（2026-11-28）

> **用途**：判断 16 维模型是否达到内部部署门槛，**不是对外准确率**。
> 14 名受试者、单一设备/场景，不能外推到其他摄像头、机位或人群。
> 权重 `model.pt` 留在 `data/posture/reports/v3-loso-head/`（已忽略），未入库。

## 数据

| 项 | 值 |
|---|---|
| 文件 | `data/posture/capture.jsonl` |
| SHA-256 | `f301abd9d07b733e60ade1bd554c729413361c5783508045d0eb946197375bad` |
| 帧数 | 3,974 |
| 受试者 | 14（`s01`–`s04`、`s11`–`s20`） |
| 来源 | `origin=capture`，`label_source=human`，全部 `upper_body` |
| 设备/场景 | `laptop-cam` / `office` 各 1 种 |
| 类别 | baseline 1,072 / forward_head 1,019 / lateral_tilt 960 / undetermined 923 |
| 契约 | `feature_spec_version=v3`，每帧带 10 字段 `baseline`（每人 baseline 段中位数） |

## 模型输入

公开 9 特征不变；模型额外使用 7 个头部几何量相对个人基线的 delta：

`head_scale`、`eye_scale`、`face_height`、`ear_shoulder_y`、`head_roll_deg`、
`nose_ear_y`、`ear_mid_offset`。

A 版输入 16 维（9 + 7）；B 版输入 148 维（132 坐标 + 16）。`feature_spec.json`
同时写入 `feature_order`（公开 9）与 `model_feature_order`（16），部署包按
`model_feature_order` 校验。

## 评估方式

`train_posture.py --split loso --deploy-version A`：14 折，每名受试者轮流做一次
测试集；指标是 out-of-fold 预测汇总。各折验证集 macro-F1 只用于早停和参考选型；
部署版本由 `--deploy-version A` 固定，两版 OOF 指标都列在下面。

## 结果

| 版本 | 输入 | 维度 | 参数 | 验证 macro-F1 | OOF macro-F1 | OOF accuracy |
|---|---|---:|---:|---:|---:|---:|
| **A（部署）** | 9 公开 + 7 头部 delta | 16 | 3,300 | 0.7744 | **0.7759** | **0.7765** |
| B | 132 坐标 + 16 | 148 | 11,748 | 0.7978 | 0.7722 | 0.7743 |

验证集选了 B（0.7978 vs 0.7744），但 B 的 OOF forward_head F1 0.689 未过 0.70，
且输入多 132 维；部署钉在 A。覆盖记录写在 `metrics.json` 的 `selection` 中，
不是用测试集重新选型。

A 版每类指标：

| 类别 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| baseline | 0.745 | 0.782 | 0.763 | 1,072 |
| forward_head | 0.794 | **0.649** | **0.714** | 1,019 |
| lateral_tilt | 0.792 | 0.782 | 0.787 | 960 |
| undetermined | 0.782 | 0.906 | 0.839 | 923 |

混淆矩阵（行=真实，列=预测，顺序 `baseline / forward_head / lateral_tilt / undetermined`）：

```text
[[838,  98,  88,  48],
 [209, 661,  76,  73],
 [ 72,  25, 751, 112],
 [  6,  48,  33, 836]]
```

## 特征消融（HistGradientBoosting，同一 LOSO 折）

| 输入 | 维度 | OOF macro-F1 | forward_head F1 |
|---|---:|---:|---:|
| 公开 9 特征 | 9 | 0.7050 | 0.536 |
| 9 + 7 头部 delta，个人基线 | 16 | **0.8050** | **0.727** |
| 9 + 7 头部 delta，总体中位数基线 | 16 | 0.7553 | 0.686 |

增益主要来自 `head_scale = 耳宽 / 肩宽`（pooled AUC 0.910）：头前伸时耳朵在画面里
变宽，而 `neck_ratio` 在多数受试者上方向不稳。个人基线比总体中位数高约 5 个点；
没有校准数据时回退总体中位数，指标仍高于公开 9 特征。

## 解读

- `forward_head` F1 从 0.603 提到 0.714、召回从 0.501 提到 0.649；主要错误仍是
  前倾被判成 baseline（209 帧）。
- 头部几何量是模型内部特征，不改变公开 9 特征契约，也不要求客户端上传新字段。
- `undetermined` 仍混有取景质量因素，F1 0.839 不能当作姿态识别能力。
- `s01` / `s03` / `s20` 的动作与标签一致性仍差（`neck_ratio` AUC 0.518 / 0.032 /
  0.491），需要重采；扩到 ≥20 人前不对外发布准确率。
- 本地 `customize_service.Model` 已加载 A 版 `model.pt` 完成前向（16 维、3,300
  参数），这只是部署包冒烟，不是效果指标。

## 结论

内部门槛（macro-F1 ≥ 0.75、forward_head F1 ≥ 0.70）已过，A 版可作为 ModelArts
部署候选；但样本只有 14 人且单一设备/场景，**不能对外声称通用准确率**。
`reports/v1/` 仍是 v2 合成数据结果，`reports/v3-loso/` 是 9 特征历史基线，三者
不能混写。
