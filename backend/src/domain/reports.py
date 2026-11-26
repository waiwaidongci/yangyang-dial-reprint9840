"""Prepare scalar rows for the review screen and CSV export."""

from .encoding import EncodedRow, History, smoothed_rate
from .settings import FEATURES, FIELDS

TRACE_LABELS = {
    "id": FIELDS["id"],
    "batch_id": FIELDS["batch_id"],
    "plate_code": FIELDS["plate_code"],
    "ink_code": FIELDS["ink_code"],
    "reference_rate": "参考返印率",
    "plate_code_rate": "印版编码",
    "plate_code_support": "印版参考件数",
    "ink_code_rate": "油墨编码",
    "ink_code_support": "油墨参考件数",
}


def table(key: str, title: str, labels: dict[str, str], rows: list[dict]) -> dict:
    return {"key": key, "title": title, "columns": list(labels), "labels": labels, "rows": rows}


def trace_values(row: EncodedRow) -> dict:
    values = {key: row.record[key] for key in ("id", "batch_id", *FEATURES)}
    values["reference_rate"] = round(row.prior, 6)
    for field, encoding in row.encodings.items():
        values[f"{field}_rate"] = round(encoding.rate, 6)
        values[f"{field}_support"] = encoding.support
    return values


def trace_table(key: str, title: str, rows: list[EncodedRow]) -> dict:
    labels = {**TRACE_LABELS, "reprint": FIELDS["reprint"]}
    return table(key, title, labels, [
        {**trace_values(row), "reprint": row.record["reprint"]} for row in rows
    ])


def review_queue(rows: list[EncodedRow], threshold: float) -> tuple[dict, int]:
    def queue_order(row: EncodedRow) -> tuple[bool, float, str]:
        return (not row.has_fallback, -row.encodings["plate_code"].rate, row.record["id"])

    prioritized = 0
    queue = []
    for position, row in enumerate(sorted(rows, key=queue_order), start=1):
        missing = [FIELDS[field] for field in FEATURES if row.encodings[field].support == 0]
        if missing:
            action = "先查新类别"
            reason = "、".join(missing) + "在历史中未见"
        elif row.encodings["plate_code"].rate >= threshold:
            action = "优先复核"
            reason = "印版编码达到优先复核线"
        else:
            action = "常规抽检"
            reason = "印版编码低于优先复核线"
        prioritized += action != "常规抽检"
        queue.append({"position": position, **trace_values(row), "action": action, "reason": reason})
    labels = {"position": "交班顺序", **TRACE_LABELS, "action": "复核安排", "reason": "判定依据"}
    return table("first_piece_queue", "印刷班首件复核名单", labels, queue), prioritized


def frozen_codebook(history: History, weight: float) -> dict:
    labels = {
        "feature": "类别字段",
        "code": "类别编号",
        "support": "历史件数",
        "reprints": "历史返印件数",
        "reference_rate": "冻结历史返印率",
        "encoded_rate": "平滑编码",
    }
    rows = []
    for field in FEATURES:
        rows.append({
            "feature": FIELDS[field], "code": "历史未见类别", "support": 0, "reprints": 0,
            "reference_rate": round(history.prior, 6), "encoded_rate": round(history.prior, 6),
        })
        for (category_field, code), count in sorted(history.categories.items()):
            if category_field == field:
                rows.append({
                    "feature": FIELDS[field], "code": code, "support": count.rows,
                    "reprints": count.positives, "reference_rate": round(history.prior, 6),
                    "encoded_rate": round(smoothed_rate(count, history.prior, weight), 6),
                })
    return table("frozen_codebook", "冻结历史编码表", labels, rows)


def comparison_table(rows: list[dict]) -> dict:
    labels = {
        "scope": "留出范围",
        "rows": "首件数",
        "reprints": "返印件数",
        "baseline_brier": "历史均值 Brier",
        "plate_code_brier": "印版编码 Brier",
        "plate_code_brier_delta": "印版减历史均值",
        "plate_code_fallbacks": "印版回退件数",
        "ink_code_brier": "油墨编码 Brier",
        "ink_code_brier_delta": "油墨减历史均值",
        "ink_code_fallbacks": "油墨回退件数",
    }
    return table("holdout_comparison", "留出批次误差对照", labels, rows)
