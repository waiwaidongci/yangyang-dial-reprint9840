"""Turn a merged codebook into scalar report tables for review and export."""

from .reports import table
from .settings import FEATURES, FIELDS


def shop_table(codebook: dict) -> dict:
    labels = {
        "shop": "车间编号",
        "version": "封账版次",
        "rows": "封账件数",
        "reprints": "封账返印件数",
        "batches": "涉及生产批次数",
    }
    rows = []
    for shop in sorted(codebook["shops"]):
        info = codebook["shops"][shop]
        rows.append({
            "shop": shop,
            "version": info["version"],
            "rows": info["rows"],
            "reprints": info["reprints"],
            "batches": len(info["batches"]),
        })
    return table("shop_seals", "两车间封账合计", labels, rows)


def split_batch_table(merged: dict, codebook: dict) -> dict:
    labels = {
        "batch_id": "生产批次",
        "shops": "涉及车间",
        "rows": "合并件数",
        "reprints": "合并返印件数",
        "plate_codes": "印版类别数",
        "ink_codes": "油墨类别数",
    }
    rows = []
    for batch_id in codebook["split_batches"]:
        batch = merged["batches"][batch_id]
        shops = [shop for shop, info in merged["shops"].items() if batch_id in info["batches"]]
        rows.append({
            "batch_id": batch_id,
            "shops": "、".join(sorted(shops)),
            "rows": batch["rows"],
            "reprints": batch["reprints"],
            "plate_codes": len(batch["plate_code"]),
            "ink_codes": len(batch["ink_code"]),
        })
    return table("split_batches", "跨车间生产批次", labels, rows)


def batch_fold_table(codebook: dict) -> dict:
    labels = {
        "batch_id": "生产批次",
        "feature": "类别字段",
        "code": "类别编号",
        "support": "折外参考件数",
        "reprints": "折外返印件数",
        "reference_rate": "本折参考返印率",
        "encoded_rate": "折外编码",
    }
    rows = []
    for batch in codebook["batches"]:
        for field in FEATURES:
            for code in sorted(batch[field]):
                entry = batch[field][code]
                rows.append({
                    "batch_id": batch["batch_id"],
                    "feature": FIELDS[field],
                    "code": code,
                    "support": entry["support"],
                    "reprints": entry["reprints"],
                    "reference_rate": round(batch["reference_rate"], 6),
                    "encoded_rate": round(entry["rate"], 6),
                })
    return table("batch_folds", "逐批折外编码", labels, rows)


def frozen_table(codebook: dict) -> dict:
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
            "feature": FIELDS[field],
            "code": "历史未见类别",
            "support": 0,
            "reprints": 0,
            "reference_rate": round(codebook["prior"], 6),
            "encoded_rate": round(codebook["unseen_rate"], 6),
        })
        for code in sorted(codebook["frozen"][field]):
            entry = codebook["frozen"][field][code]
            rows.append({
                "feature": FIELDS[field],
                "code": code,
                "support": entry["support"],
                "reprints": entry["reprints"],
                "reference_rate": round(codebook["prior"], 6),
                "encoded_rate": round(entry["rate"], 6),
            })
    return table("frozen_codebook", "冻结历史编码表", labels, rows)


def summarize_merge(merged: dict, codebook: dict) -> dict:
    split_batches = codebook["split_batches"]
    fallback_categories = sum(
        1
        for batch in codebook["batches"]
        for field in FEATURES
        for entry in batch[field].values()
        if entry["support"] == 0
    )
    warnings = [
        "本册仅由两车间的封账合计合并而成，逐件记录仍保存在各车间。",
        "折外编码按生产批次整批扣除，跨车间批次在两边合并后整体扣除。",
    ]
    if split_batches:
        warnings.append("有生产批次分到两个车间完成，折外编码与未知类别回退已按合并后的整批扣除。")
    if fallback_categories:
        warnings.append("部分类别仅出现在被扣除的批次内，折外编码回退到本折参考返印率。")
    if codebook["reprints"] in (0, codebook["rows"]):
        warnings.append("合册历史仅有一种返印结果，编码无法据此区分类别。")
    summary = (
        f"合并 {len(codebook['shops'])} 个车间的封账合计，共 {codebook['rows']} 件历史首件、"
        f"{len(codebook['batches'])} 个生产批次逐批留出编码。"
        f"其中 {len(split_batches)} 个批次分到两边做，已按合并后的整批扣除。"
        f"冻结历史编码后供各车间编码留出与待检首件。"
    )
    return {
        "summary": summary,
        "metrics": {
            "合册总件数": codebook["rows"],
            "合册返印件数": codebook["reprints"],
            "合册返印率": round(codebook["prior"], 6),
            "冻结历史返印率": round(codebook["prior"], 6),
            "跨车间批次数": len(split_batches),
            "平滑权重": codebook["smoothing"],
        },
        "versions": {shop: codebook["shops"][shop]["version"] for shop in sorted(codebook["shops"])},
        "tables": [
            shop_table(codebook),
            split_batch_table(merged, codebook),
            frozen_table(codebook),
            batch_fold_table(codebook),
        ],
        "warnings": warnings,
    }
