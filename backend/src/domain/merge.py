"""Merge sealed shop aggregates into one shared reprint codebook.

Each shop keeps its per-piece register locally.  The only thing exchanged is a
sealed aggregate: for every production batch its row/reprint totals and, for
every plate and ink code, the row/reprint counts inside that batch.  A
production batch that both shops work on therefore arrives as two partial
aggregates that simply add up.

Out-of-fold encodings remove the *whole* combined batch from the reference, no
matter which shop holds which piece.  A category that only occurs inside that
excluded batch has zero out-of-fold support and falls back to the fold's
reference reprint rate.  Because the aggregate keeps per-batch category counts,
the merged folds reproduce exactly what one grouped split over the full local
register would give, without ever sharing a per-piece record.
"""

from collections import defaultdict

from .encoding import EncodedRow, Encoding, TargetCount, smoothed_rate
from .records import CODE, parse_code, parse_reprint
from .settings import COLUMNS, FEATURES, FIELDS

DEFAULT_SMOOTHING = 8
HISTORY_SPLIT = "train"
MIN_BATCHES = 2


def normalize_shop(value) -> str:
    if isinstance(value, str) and CODE.fullmatch(value.strip()):
        return value.strip()
    raise ValueError("车间编号须为 1 至 64 位编号，以英文字母或数字开头。")


def _as_int(value, message: str) -> int:
    if type(value) is bool or not isinstance(value, (int, str)):
        raise ValueError(message)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(message) from None
    if isinstance(value, str) and value.strip() != str(parsed):
        raise ValueError(message)
    return parsed


def _counter() -> dict:
    return {"rows": 0, "reprints": 0}


def _batch() -> dict:
    return {"rows": 0, "reprints": 0, "plate_code": defaultdict(_counter), "ink_code": defaultdict(_counter)}


def seal_from_rows(rows: list[dict], shop, version=None) -> dict:
    """Reduce one shop's local history rows to the aggregate it exchanges.

    This helper never leaves the shop: only its return value is handed over.
    """

    shop = normalize_shop(shop)
    seen = set()
    batches: dict[str, dict] = {}
    for line, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict) or raw.keys() != set(COLUMNS):
            raise ValueError(f"第 {line} 条的列须与模板一致：{', '.join(COLUMNS)}。")
        record_id = parse_code(raw["id"], FIELDS["id"], line)
        if record_id in seen:
            raise ValueError(f"第 {line} 条的首件记录号 {record_id} 重复。")
        seen.add(record_id)
        split = raw["split"].strip() if isinstance(raw["split"], str) else None
        if split != HISTORY_SPLIT:
            raise ValueError(f"第 {line} 条封账数只收已确认历史件，样本用途须为 {HISTORY_SPLIT}。")
        batch_id = parse_code(raw["batch_id"], FIELDS["batch_id"], line)
        plate = parse_code(raw["plate_code"], FIELDS["plate_code"], line)
        ink = parse_code(raw["ink_code"], FIELDS["ink_code"], line)
        target = parse_reprint(raw["reprint"], split, line)
        bucket = batches.setdefault(batch_id, _batch())
        bucket["rows"] += 1
        bucket["reprints"] += target
        for field, code in (("plate_code", plate), ("ink_code", ink)):
            counted = bucket[field][code]
            counted["rows"] += 1
            counted["reprints"] += target
    if not batches:
        raise ValueError("封账数至少需要一条已确认历史件。")
    return _finalize_seal(shop, batches, version)


def _finalize_seal(shop: str, batches: dict, version=None) -> dict:
    total_rows = sum(batch["rows"] for batch in batches.values())
    total_reprints = sum(batch["reprints"] for batch in batches.values())
    clean = {}
    for batch_id in sorted(batches):
        batch = batches[batch_id]
        clean[batch_id] = {
            "rows": batch["rows"],
            "reprints": batch["reprints"],
            **{field: {code: dict(count) for code, count in batch[field].items()} for field in FEATURES},
        }
    seal = {"shop": shop, "rows": total_rows, "reprints": total_reprints, "batches": clean}
    if version is not None:
        seal["version"] = version
    return seal


def validate_seal(seal: dict) -> dict:
    """Check an aggregate loaded from storage or received over the wire."""

    if not isinstance(seal, dict):
        raise ValueError("封账数须为一个对象。")
    shop = normalize_shop(seal.get("shop"))
    batches = seal.get("batches")
    if not isinstance(batches, dict) or not batches:
        raise ValueError("封账数缺少生产批次合计。")
    rebuilt = {}
    for raw_batch_id, batch in batches.items():
        batch_id = parse_code(raw_batch_id, FIELDS["batch_id"], 0)
        if batch_id in rebuilt:
            raise ValueError(f"生产批次 {batch_id} 在封账数中重复出现。")
        if not isinstance(batch, dict):
            raise ValueError(f"生产批次 {batch_id} 的合计格式有误。")
        bucket = _batch()
        bucket["rows"] = _as_int(batch.get("rows"), f"生产批次 {batch_id} 的件数无效。")
        bucket["reprints"] = _as_int(batch.get("reprints"), f"生产批次 {batch_id} 的返印件数无效。")
        if bucket["rows"] <= 0 or not 0 <= bucket["reprints"] <= bucket["rows"]:
            raise ValueError(f"生产批次 {batch_id} 的件数或返印件数无效。")
        for field in FEATURES:
            source = batch.get(field, {})
            if not isinstance(source, dict):
                raise ValueError(f"生产批次 {batch_id} 的{FIELDS[field]}合计格式有误。")
            for raw_code, count in source.items():
                code = parse_code(raw_code, FIELDS[field], 0)
                if code in bucket[field]:
                    raise ValueError(f"生产批次 {batch_id} 的{code}重复出现。")
                if not isinstance(count, dict):
                    raise ValueError(f"生产批次 {batch_id} 的{code}计数格式有误。")
                rows = _as_int(count.get("rows"), f"生产批次 {batch_id} 的{code}件数无效。")
                reprints = _as_int(count.get("reprints"), f"生产批次 {batch_id} 的{code}返印件数无效。")
                if rows <= 0 or not 0 <= reprints <= rows:
                    raise ValueError(f"生产批次 {batch_id} 的{code}件数或返印件数无效。")
                bucket[field][code] = {"rows": rows, "reprints": reprints}
            if sum(item["rows"] for item in bucket[field].values()) != bucket["rows"]:
                raise ValueError(f"生产批次 {batch_id} 的{FIELDS[field]}件数与批次合计不一致。")
            if sum(item["reprints"] for item in bucket[field].values()) != bucket["reprints"]:
                raise ValueError(f"生产批次 {batch_id} 的{FIELDS[field]}返印件数与批次合计不一致。")
        rebuilt[batch_id] = bucket
    total = sum(b["rows"] for b in rebuilt.values())
    reprints = sum(b["reprints"] for b in rebuilt.values())
    if "rows" in seal and _as_int(seal["rows"], "封账数总件数无效。") != total:
        raise ValueError("封账数的总件数与各批合计不一致。")
    if "reprints" in seal and _as_int(seal["reprints"], "封账数总返印件数无效。") != reprints:
        raise ValueError("封账数的总返印件数与各批合计不一致。")
    return _finalize_seal(shop, rebuilt, seal.get("version"))


def merge_seals(seals: list[dict]) -> dict:
    """Add up the exchanged aggregates of the participating shops."""

    if not isinstance(seals, list) or not seals:
        raise ValueError("合册至少需要一份封账数。")
    shops: dict[str, dict] = {}
    batches: dict[str, dict] = {}
    total_rows = 0
    total_reprints = 0
    for seal in seals:
        checked = validate_seal(seal)
        shop = checked["shop"]
        if shop in shops:
            raise ValueError(f"车间 {shop} 在一次合册中只能有一份封账数。")
        shops[shop] = {
            "version": seal.get("version"),
            "rows": checked["rows"],
            "reprints": checked["reprints"],
            "batches": sorted(checked["batches"]),
        }
        total_rows += checked["rows"]
        total_reprints += checked["reprints"]
        for batch_id, batch in checked["batches"].items():
            target = batches.setdefault(batch_id, _batch())
            target["rows"] += batch["rows"]
            target["reprints"] += batch["reprints"]
            for field in FEATURES:
                for code, count in batch[field].items():
                    counted = target[field][code]
                    counted["rows"] += count["rows"]
                    counted["reprints"] += count["reprints"]
    clean = {}
    for batch_id in sorted(batches):
        batch = batches[batch_id]
        clean[batch_id] = {
            "rows": batch["rows"],
            "reprints": batch["reprints"],
            **{field: {code: dict(count) for code, count in batch[field].items()} for field in FEATURES},
        }
    return {"rows": total_rows, "reprints": total_reprints, "shops": shops, "batches": clean}


def split_batches(merged: dict) -> list[str]:
    """Production batches that both shops worked on."""

    holders = defaultdict(int)
    for shop in merged["shops"].values():
        for batch_id in shop["batches"]:
            holders[batch_id] += 1
    return sorted(batch_id for batch_id, count in holders.items() if count > 1)


def build_codebook(merged: dict, smoothing: float = DEFAULT_SMOOTHING) -> dict:
    """Turn a merged aggregate into the frozen codebook plus per-batch folds."""

    total_rows = merged["rows"]
    total_reprints = merged["reprints"]
    if total_rows <= 0:
        raise ValueError("合册历史件数为 0，无法生成编码册。")
    if len(merged["batches"]) < MIN_BATCHES:
        raise ValueError("逐批留出至少需要两个生产批次的合计，请等两边交齐后再开算。")

    prior = total_reprints / total_rows
    global_categories: dict[str, dict] = {field: {} for field in FEATURES}
    for batch in merged["batches"].values():
        for field in FEATURES:
            for code, count in batch[field].items():
                target = global_categories[field].setdefault(code, _counter())
                target["rows"] += count["rows"]
                target["reprints"] += count["reprints"]

    frozen = {}
    for field in FEATURES:
        frozen[field] = {
            code: {
                "rows": count["rows"],
                "reprints": count["reprints"],
                "support": count["rows"],
                "rate": smoothed_rate(TargetCount(count["rows"], count["reprints"]), prior, smoothing),
            }
            for code, count in sorted(global_categories[field].items())
        }

    batches = []
    for batch_id in sorted(merged["batches"]):
        batch = merged["batches"][batch_id]
        reference_rows = total_rows - batch["rows"]
        reference_reprints = total_reprints - batch["reprints"]
        reference_rate = reference_reprints / reference_rows if reference_rows else prior
        folds = {}
        for field in FEATURES:
            folds[field] = {}
            for code in sorted(batch[field]):
                whole = global_categories[field][code]
                support = whole["rows"] - batch[field][code]["rows"]
                reprints = whole["reprints"] - batch[field][code]["reprints"]
                folds[field][code] = {
                    "support": support,
                    "reprints": reprints,
                    "rate": smoothed_rate(TargetCount(support, reprints), reference_rate, smoothing),
                }
        batches.append({
            "batch_id": batch_id,
            "rows": batch["rows"],
            "reprints": batch["reprints"],
            "reference_rows": reference_rows,
            "reference_reprints": reference_reprints,
            "reference_rate": reference_rate,
            "plate_code": folds["plate_code"],
            "ink_code": folds["ink_code"],
        })

    return {
        "smoothing": smoothing,
        "rows": total_rows,
        "reprints": total_reprints,
        "prior": prior,
        "unseen_rate": prior,
        "shops": merged["shops"],
        "split_batches": split_batches(merged),
        "frozen": frozen,
        "batches": batches,
        "batch_index": {batch["batch_id"]: batch for batch in batches},
    }


def encode_row(codebook: dict, row: dict) -> EncodedRow:
    """Apply the shared codebook to one locally held row.

    History rows use their batch's out-of-fold entry, which already removed the
    whole combined batch.  Holdout and pending rows are not part of any folded
    batch and use the frozen table; a code unseen in the merged history falls
    back to the frozen reference rate with support 0.
    """

    index = codebook.get("batch_index")
    if index is None:
        index = {batch["batch_id"]: batch for batch in codebook["batches"]}
    batch = index.get(row["batch_id"])
    history = row.get("split") == HISTORY_SPLIT
    encodings = {}
    if history and batch is not None:
        prior = batch["reference_rate"]
        for field in FEATURES:
            entry = batch[field].get(row[field])
            if entry is None:
                entry = codebook["frozen"][field].get(row[field])
                encodings[field] = Encoding(entry["rate"], entry["support"]) if entry else Encoding(prior, 0)
            else:
                encodings[field] = Encoding(entry["rate"], entry["support"])
    else:
        prior = codebook["unseen_rate"]
        for field in FEATURES:
            entry = codebook["frozen"][field].get(row[field])
            encodings[field] = Encoding(entry["rate"], entry["support"]) if entry else Encoding(prior, 0)
    return EncodedRow(row, prior, encodings)


def apply_codebook(codebook: dict, rows: list[dict]) -> list[EncodedRow]:
    return [encode_row(codebook, row) for row in rows]
