# ModelArts 姿态模型：训练包对接层

云端契约只有一份：`apps/cloud-api/app/schemas/posture.py` 与
`app/services/posture_features.py`。训练包不再保留契约副本。

## 文件

| 文件 | 作用 | 能否进 ModelArts 模型包 |
|---|---|---|
| `posture_contract.py` | 从 cloud-api 取 33 点、6 特征、类别、阈值；训练与校验用 | 否 |
| `posture_runtime.py` | 部署副本：纯 Python 特征提取与响应组装，无 torch | 是 |
| `label_policy.py` | 标注口径（预标注/合成数据）；引用 mock 阈值 | 否 |
| `dataset_check.py` | jsonl 校验：契约、特征一致性、标签、禁止字段 | 否 |

`posture_runtime.py` 是唯一允许的重复，因为 ModelArts 只能上传模型目录。
`apps/cloud-api/tests/test_modelarts_contract_parity.py` 用 300 组随机关键点
锁定两份实现，并校验数据集里的特征与关键点自洽。

## 用法

```bash
python scripts/modelarts/dataset_check.py data/posture/frames.jsonl
python -m pytest -q
```

`dataset_check.py` 退出码 0 才允许训练。它会拒绝：关键点数量/顺序不符、
`features` 与关键点重算结果差 >1e-3、未知类别、`image`/`base64` 等画面字段。

## 合并训练包的规则

1. 删除自带的 `contract.py` 与常量表，改为 `from posture_contract import ...`。
2. 推理包里内联的特征逻辑一律放 `posture_runtime.py`，`customize_service.py`
   只做 torch 推理；禁止在 `customize_service.py` 里再抄一份公式。
3. `customize_service.py` 必须导出 `FEATURE_SPEC_VERSION = "v1"` 与
   `features_from_keypoints`，便于测试对账。
4. 不改 `apps/cloud-api/**`、`packages/**`。发现差异改训练侧，不改服务端。
5. 合成数据必须走 `label_policy.prelabel`，并在 `metrics.json` 记录
   `policy.version`；禁止另写一套阈值。
6. 数据与权重不进 git（`artifacts/`、`data/posture/` 已忽略）。

## 指标口径

- `synthetic` 只证明管线可复现，不能对外称准确率。
- `capture` 帧按 `subject` 分组划分，同一人不得跨训练与测试。
- 报告必须同时给 macro-F1、每类 P/R/F1、混淆矩阵、样本来源与受试者数。
