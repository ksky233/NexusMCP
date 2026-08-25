"""Identity 上下文的 SQLAlchemy Model。"""

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="status"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )
