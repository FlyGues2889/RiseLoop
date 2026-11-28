# v3 特征契约内部 LOSO 报告（2026-11-26）

> **已被 `reports/v3-loso-head/` 取代（2026-11-28）**：16 维模型 A 版 OOF macro-F1
> 0.7759、forward_head F1 0.7142。本文件保留为 9 特征基线与重采前的历史记录，
> 不再作为部署依据。
>
> **用途**：判断 v3 特征与当前标签是否值得继续投入，**不是对外准确率**。
> 14 名受试者、单一设备/场景，不能外推到其他摄像头、机位或人群。
> 权重 `model.pt` 留在 `data/posture/reports/v3-loso/`（已忽略），未入库。

## 数据

| 项 | 值 |
|---|---|
| 文件 | `data/posture/capture.jsonl` |
| SHA-256 | `89b8e1fa11564bf4787fd1ff343e7647c871f8d9b5fff8a5896a8c498c04fc64` |
| 帧数 | 3,974 |
| 受试者 | 14（`s01`–`s04`、`s11`–`s20`） |
| 来源 | `origin=capture`，`label_source=human`，全部 `upper_body` |
| 设备/场景 | `laptop-cam` / `office` 各 1 种 |
| 类别 | baseline 1,072 / forward_head 1,019 / lateral_tilt 960 / undetermined 923 |
| 契约 | `feature_spec_version=v3`，每帧带 `baseline` |

## 评估方式

`train_posture.py --split loso`：14 折，每名受试者轮流做一次测试集；报告中的指标是
out-of-fold 预测汇总，不是单次 70/15/15 的 2 人测试集。

## 结果

| 版本 | 输入 | 维度 | 参数 | OOF macro-F1 | OOF accuracy |
|---|---|---:|---:|---:|---:|
| A | 9 个 2D 特征 | 9 | 2,852 | 0.7146 | 0.7159 |
| **B（选中）** | 132 坐标 + 9 个 2D 特征 | 141 | 11,300 | **0.7305** | **0.7323** |

选型只看各折验证集 macro-F1 的均值（A 0.7235 / B 0.7685），测试集只用于报告。

B 版每类指标：

| 类别 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| baseline | 0.619 | 0.746 | 0.677 | 1,072 |
| forward_head | 0.755 | **0.501** | 0.603 | 1,019 |
| lateral_tilt | 0.773 | 0.756 | 0.765 | 960 |
| undetermined | 0.820 | 0.946 | 0.878 | 923 |

混淆矩阵（行=真实，列=预测，顺序 `baseline / forward_head / lateral_tilt / undetermined`）：

```text
[[800, 125,  74,  73],
 [326, 511, 122,  60],
 [145,  30, 726,  59],
 [ 22,  11,  17, 873]]
```

## 解读

- 比之前固定 70/15/15 的 0.429 / 0.589 稳定得多，说明 v3 特征和 LOSO 口径有效。
- `forward_head` 召回只有 0.501：1,019 帧里有 326 帧被判成 `baseline`。前倾仍是弱项，
  不能因为 macro-F1 过 0.70 就认为可用。
- `undetermined` F1 0.878，主要来自取景质量；它更像质量门控，而不是稳定的姿态类别。
- B 版包含 132 维坐标，说明模型仍依赖原始几何；9 个可解释特征单独只有 0.7146。
  对外解释时不能只说“模型只看 9 个特征”。
- 本地 `customize_service.Model` 已能加载 B 版 `model.pt`，接受 `keypoints + baseline`
  并完成前向；这只是部署包冒烟，不是效果指标。

## 结论

**可以继续，但还不能发布。**

内部 LOSO 达到约定门槛（macro-F1 ≥ 0.70、forward_head F1 ≥ 0.60），但 forward_head
召回偏低、只有 14 人且单一设备。下一步应优先：

1. 重采 `s01` / `s03` / `s20`，扩到 ≥20 人；
2. 补个人基线校准，验证线上 `baseline` 与训练时口径一致；
3. 用扩样后的数据重跑 LOSO，forward_head F1 稳定过 0.65 再考虑接真实 endpoint。

`reports/v1/` 仍是 v2 合成数据结果，不能和本报告混写。
