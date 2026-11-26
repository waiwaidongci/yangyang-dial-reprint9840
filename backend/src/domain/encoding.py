"""Fit category counts and produce encodings from production-batch complements."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .settings import FEATURES


@dataclass(frozen=True)
class TargetCount:
    rows: int = 0
    positives: int = 0

    def __sub__(self, other: "TargetCount") -> "TargetCount":
        return TargetCount(self.rows - other.rows, self.positives - other.positives)


@dataclass(frozen=True)
class Encoding:
    rate: float
    support: int


@dataclass(frozen=True)
class History:
    total: TargetCount
    categories: Mapping[tuple[str, str], TargetCount]

    @property
    def prior(self) -> float:
        return self.total.positives / self.total.rows

    def transform(self, row: dict, weight: float, excluded: "History | None" = None) -> "EncodedRow":
        reference = self.total if excluded is None else self.total - excluded.total
        prior = reference.positives / reference.rows
        encodings = {}
        for field in FEATURES:
            key = (field, row[field])
            count = self.categories.get(key, TargetCount())
            if excluded is not None:
                count -= excluded.categories.get(key, TargetCount())
            encodings[field] = Encoding(smoothed_rate(count, prior, weight), count.rows)
        return EncodedRow(row, prior, encodings)


@dataclass(frozen=True)
class EncodedRow:
    record: dict
    prior: float
    encodings: dict[str, Encoding]

    @property
    def has_fallback(self) -> bool:
        return any(encoding.support == 0 for encoding in self.encodings.values())


def smoothed_rate(count: TargetCount, prior: float, weight: float) -> float:
    if count.rows == 0:
        return prior
    return (count.positives + weight * prior) / (count.rows + weight)


def fit_history(rows: list[dict]) -> History:
    row_counts = Counter()
    positive_counts = Counter()
    positives = 0
    for row in rows:
        target = row["reprint"]
        positives += target
        for field in FEATURES:
            key = (field, row[field])
            row_counts[key] += 1
            positive_counts[key] += target
    categories = {key: TargetCount(count, positive_counts[key]) for key, count in row_counts.items()}
    return History(TargetCount(len(rows), positives), MappingProxyType(categories))


def grouped_out_of_fold(rows: list[dict], history: History, weight: float) -> list[EncodedRow]:
    batches = defaultdict(list)
    for row in rows:
        batches[row["batch_id"]].append(row)
    excluded_batches = {batch: fit_history(group) for batch, group in batches.items()}
    return [history.transform(row, weight, excluded_batches[row["batch_id"]]) for row in rows]
