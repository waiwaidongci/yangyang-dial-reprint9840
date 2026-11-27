"""Input columns and settings shared by the domain and the application."""

COLUMNS = ("id", "batch_id", "split", "plate_code", "ink_code", "reprint")
FEATURES = ("plate_code", "ink_code")
FIELDS = {
    "id": "首件记录号",
    "batch_id": "生产批次",
    "split": "样本用途",
    "plate_code": "印版编号",
    "ink_code": "油墨编号",
    "reprint": "已确认返印",
}
SETTINGS = [
    {"key": "smoothing", "label": "平滑权重（等效历史件数）", "default": 8,
     "min": 1, "max": 50, "step": 1},
    {"key": "review_threshold", "label": "首件优先复核线", "default": 0.5,
     "min": 0, "max": 1, "step": 0.01},
]

SPEC = {
    "columns": list(COLUMNS),
    "fields": FIELDS,
    "settings": SETTINGS,
    "modules": {
        "datasets": "首件来源台账",
        "runs": "编码运行",
        "results": "返印编码册",
        "reviews": "交班复核",
        "merge": "两车间合册",
    },
    "limitation": "留出对照仅反映本次已留批次。少量返印和回退样本会影响结果，新类别需由印刷班核对。",
    "dataset_name": "20261125-字盘首件交班.csv",
    "recommendation": "先核对新印版和新油墨，再按印版编码复核达到优先线的待检首件。",
    "merge": {
        "exchanged": "各生产批次的件数与返印件数，及批内各印版、各油墨的件数与返印件数。",
        "per_piece": "逐件记录由各车间本地留存，不上传。",
        "smoothing_default": 8,
        "fold": "同一生产批次分到两边做时，按合并后的整批扣除折外参考；类别仅在被扣除批次出现时回退到本折参考返印率。",
        "lifecycle": "两边封账数交齐才开算；开算固定两份封账版次；补报以新版次保存；中断按原版次恢复，同版次不新增编码册。",
    },
}


def parse_settings(settings: dict) -> dict[str, float]:
    parsed = {}
    for spec in SETTINGS:
        value = settings.get(spec["key"], spec["default"])
        if type(value) not in (int, float) or not spec["min"] <= value <= spec["max"]:
            raise ValueError(f'{spec["label"]}须为 {spec["min"]} 至 {spec["max"]} 之间的数值。')
        parsed[spec["key"]] = float(value)
    return parsed
