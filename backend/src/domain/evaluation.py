"""Compare fixed encodings with the same historical prior on held-out labels."""

from collections import defaultdict
from math import fsum

from .encoding import EncodedRow
from .settings import FEATURES


def compare_holdout(scope: str, rows: list[EncodedRow]) -> dict:
    targets = [row.record["reprint"] for row in rows]
    baseline = fsum((row.prior - target) ** 2 for row, target in zip(rows, targets)) / len(rows)
    result = {
        "scope": scope,
        "rows": len(rows),
        "reprints": sum(targets),
        "baseline_brier": round(baseline, 6),
    }
    for field in FEATURES:
        rates = [row.encodings[field] for row in rows]
        loss = fsum((encoding.rate - target) ** 2 for encoding, target in zip(rates, targets)) / len(rows)
        result[f"{field}_brier"] = round(loss, 6)
        result[f"{field}_brier_delta"] = round(loss - baseline, 6)
        result[f"{field}_fallbacks"] = sum(encoding.support == 0 for encoding in rates)
    return result


def holdout_diagnostics(holdout: list[EncodedRow]) -> tuple[list[dict], list[str]]:
    batches = defaultdict(list)
    for row in holdout:
        batches[row.record["batch_id"]].append(row)
    pooled = compare_holdout("全部留出批次", holdout)
    comparison = [pooled, *(compare_holdout(batch, rows) for batch, rows in sorted(batches.items()))]
    warnings = ["Brier 分数越低，表示对本次留出标签的平均平方误差越小。请结合逐批结果、返印件数和回退件数复核。"]
    if len(batches) < 5 or len(holdout) < 30:
        warnings.append("本次留出覆盖的批次或件数较少，少数记录可能明显改变对照结果。")
    if pooled["reprints"] in (0, pooled["rows"]):
        warnings.append("本次留出仅有一种返印结果，无法核查对两类首件的区分情况。")
    if any(row.has_fallback for row in holdout):
        warnings.append("留出中有历史未见类别，其对应编码使用冻结历史返印率，已计入误差对照。")
    return comparison, warnings
