from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class ShopSeal(Base):
    """One shop's sealed aggregate. Per-piece rows are never stored here."""

    __tablename__ = 'shop_seals'
    __table_args__ = (UniqueConstraint('shop', 'version', name='uq_shop_seal_version'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    reprints: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
