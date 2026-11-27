from pydantic import BaseModel, ConfigDict, Field

from src.constants.workflow import Decision


class MergeReviewCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: Decision
    note: str = Field(min_length=4, max_length=1000)


class MergeReviewInfo(MergeReviewCreate):
    book_id: int
    created_at: str
