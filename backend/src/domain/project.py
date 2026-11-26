"""Domain entry points for the application and its background worker."""

from .encoding import fit_history, grouped_out_of_fold
from .evaluation import holdout_diagnostics
from .fixtures import demo_rows
from .records import normalize_rows
from .reports import comparison_table, frozen_codebook, review_queue, trace_table
from .settings import SPEC, parse_settings

__all__ = ["SPEC", "demo_rows", "normalize_rows", "analyze"]


def analyze(rows: list[dict], settings: dict) -> dict:
    options = parse_settings(settings)
    ordered = sorted(normalize_rows(rows), key=lambda row: row["id"])
    train = [row for row in ordered if row["split"] == "train"]
    weight = options["smoothing"]
    history = fit_history(train)
    historical_encodings = grouped_out_of_fold(train, history, weight)
    holdout = [history.transform(row, weight) for row in ordered if row["split"] == "holdout"]
    pending = [history.transform(row, weight) for row in ordered if row["split"] == "pending"]
    comparison, warnings = holdout_diagnostics(holdout)
    queue, prioritized = review_queue(pending, options["review_threshold"])
    historical_batches = len({row["batch_id"] for row in train})
    if history.total.positives in (0, history.total.rows):
        warnings.append("历史拟合样本仅有一种返印结果，编码无法据此区分类别。")
    if any(row.has_fallback for row in historical_encodings):
        warnings.append("部分历史类别只在一个批次出现，折外编码使用其余批次的返印率。")
    if not pending:
        warnings.append("本次未导入待检首件，交班名单为空。")
    return {
        "summary": (
            f"{len(train)} 件历史首件按 {historical_batches} 个生产批次逐批留出编码。"
            f"冻结历史编码后，在 {len(comparison) - 1} 个留出批次共 {len(holdout)} 件上"
            f"对照历史均值、印版编码与油墨编码的 Brier 分数。"
            f"{len(pending)} 件待检首件中有 {prioritized} 件需先查新类别或优先复核。"
        ),
        "metrics": {
            "冻结历史返印率": round(history.prior, 6),
            "优先处理首件数": prioritized,
            "留出历史均值 Brier": comparison[0]["baseline_brier"],
            "留出印版 Brier": comparison[0]["plate_code_brier"],
            "留出油墨 Brier": comparison[0]["ink_code_brier"],
        },
        "tables": [
            queue,
            comparison_table(comparison),
            trace_table("historical_out_of_fold", "历史分组折外编码", historical_encodings),
            trace_table("holdout_encodings", "留出件编码明细", holdout),
            frozen_codebook(history, weight),
        ],
        "warnings": warnings,
    }
