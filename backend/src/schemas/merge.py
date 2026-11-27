from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, constr

from src.constants.workflow import MergeStatus


class SealSubmit(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    shop: Annotated[str, constr(min_length=1, max_length=64)] | None = None
    version: int | None = Field(default=None, ge=1)
    csv: str | None = Field(default=None, min_length=5, max_length=600_000)
    payload: dict | None = None


class SealInfo(BaseModel):
    id: int
    shop: str
    version: int
    rows: int
    reprints: int
    batches: int
    checksum: str
    created_at: str


class SealDetail(SealInfo):
    payload: dict


class SealRef(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    shop: Annotated[str, constr(min_length=1, max_length=64)]
    version: int | None = Field(default=None, ge=1)


class BookCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str = Field(min_length=2, max_length=140)
    seals: list[SealRef] | None = Field(default=None, max_length=2)


class BookInfo(BaseModel):
    id: int
    label: str
    status: MergeStatus
    smoothing: float
    versions: dict[str, int]
    seals: list[dict]
    created_at: str
    updated_at: str
    decision: str | None


class LocalEncode(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    shop: Annotated[str, constr(min_length=1, max_length=64)]
    review_threshold: float = Field(default=0.5, ge=0, le=1)
    rows: list[dict] = Field(min_length=1, max_length=5000)
