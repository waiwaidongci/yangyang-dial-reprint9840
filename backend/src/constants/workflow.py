from enum import StrEnum


class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class RunStatus(StrEnum):
    COMPLETED = 'completed'
    FAILED = 'failed'


class MergeStatus(StrEnum):
    SEALED = 'sealed'          # both seals present and locked for this version pair
    CALCULATING = 'calculating'
    READY = 'ready'            # result computed, awaiting review
    APPROVED = 'approved'
    REJECTED = 'rejected'
    FAILED = 'failed'


class Decision(StrEnum):
    APPROVED = 'approved'
    REJECTED = 'rejected'
