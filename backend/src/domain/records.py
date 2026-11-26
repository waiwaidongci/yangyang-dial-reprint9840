"""Parse site identifiers and keep production batches within one cohort."""

import re
from collections import Counter

from .settings import COLUMNS, FIELDS

CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SPLITS = {"train": "历史拟合", "holdout": "留出评估", "pending": "待检首件"}


def parse_code(value, label: str, line: int) -> str:
    if isinstance(value, str) and CODE.fullmatch(value.strip()):
        return value.strip()
    raise ValueError(f"第 {line} 条的{label}须为 1 至 64 位编号，以英文字母或数字开头。")


def parse_reprint(value, split: str, line: int) -> int | None:
    if isinstance(value, str):
        value = value.strip()
    if split == "pending":
        if value is None or value == "":
            return None
        raise ValueError(f"第 {line} 条待检首件尚无确认结果，请将返印字段留空。")
    if value in ("0", "1") or (type(value) is int and value in (0, 1)):
        return int(value)
    raise ValueError(f"第 {line} 条的已确认返印须填写 0 或 1。")


def normalize_rows(rows: list[dict]) -> list[dict]:
    ids = set()
    splits_by_batch = {}
    row_counts = Counter()
    normalized = []
    for line, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict) or raw.keys() != set(COLUMNS):
            raise ValueError(f"第 {line} 条的列须与模板一致：{', '.join(COLUMNS)}。")
        record = {
            key: parse_code(raw[key], FIELDS[key], line)
            for key in ("id", "batch_id", "plate_code", "ink_code")
        }
        row_id = record["id"]
        if row_id in ids:
            raise ValueError(f"第 {line} 条的首件记录号 {row_id} 重复。")
        ids.add(row_id)
        split = raw["split"].strip() if isinstance(raw["split"], str) else None
        if split not in SPLITS:
            raise ValueError(f"第 {line} 条的样本用途须为 train、holdout 或 pending。")
        batch_id = record["batch_id"]
        if splits_by_batch.setdefault(batch_id, split) != split:
            raise ValueError(f"生产批次 {batch_id} 同时出现在不同样本用途，请整批划分。")
        record["split"] = split
        record["reprint"] = parse_reprint(raw["reprint"], split, line)
        normalized.append({key: record[key] for key in COLUMNS})
        row_counts[split] += 1

    if row_counts["train"] < 6 or sum(split == "train" for split in splits_by_batch.values()) < 3:
        raise ValueError("历史拟合至少需要 6 条已确认记录，且覆盖至少 3 个生产批次。")
    if row_counts["holdout"] < 2:
        raise ValueError("留出评估至少需要 2 条来自独立批次的已确认记录。")
    return normalized
