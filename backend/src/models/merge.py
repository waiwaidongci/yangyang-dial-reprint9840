from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class MergeBook(Base):
    """A shared reprint codebook built from two sealed shop aggregates."""

    __tablename__ = 'merge_books'
    __table_args__ = (
        UniqueConstraint('shop_low', 'version_low', 'shop_high', 'version_high',
                         name='uq_merge_seal_versions'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(140))
    shop_low: Mapped[str] = mapped_column(String(64))
    version_low: Mapped[int] = mapped_column(Integer)
    shop_high: Mapped[str] = mapped_column(String(64))
    version_high: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    smoothing: Mapped[float] = mapped_column(Float)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class MergeReview(Base):
    __tablename__ = 'merge_reviews'

    book_id: Mapped[int] = mapped_column(ForeignKey('merge_books.id'), primary_key=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
