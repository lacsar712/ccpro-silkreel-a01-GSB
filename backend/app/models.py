from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import text


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default="worker")


class Filature(Base):
    __tablename__ = "filatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    riverside: Mapped[str] = mapped_column(String(120), default="")
    basins: Mapped[list["Basin"]] = relationship(back_populates="filature")


class Basin(Base):
    __tablename__ = "basins"
    __table_args__ = (UniqueConstraint("filature_id", "code"),)

    STATUS_SOAKING = "soaking"
    STATUS_REELING = "reeling"
    STATUS_REELED = "reeled"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filature_id: Mapped[int] = mapped_column(ForeignKey("filatures.id"))
    code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=STATUS_SOAKING)
    ring_index: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    filature: Mapped[Filature] = relationship(back_populates="basins")
    readings: Mapped[list["BathReading"]] = relationship(back_populates="basin")
    tickets: Mapped[list["PenetrationTicket"]] = relationship(back_populates="basin")


class BathReading(Base):
    __tablename__ = "bath_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    basin_id: Mapped[int] = mapped_column(ForeignKey("basins.id"))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    water_temp_c: Mapped[float] = mapped_column(Float)
    operator: Mapped[str] = mapped_column(String(64), default="")
    basin: Mapped[Basin] = relationship(back_populates="readings")


class PenetrationTicket(Base):
    """渗透合格单：按盆编号，从 1 起；同盆未作废单号不得撞车。"""

    __tablename__ = "penetration_tickets"
    __table_args__ = (
        # 只对未作废单生效：同盆同号在库里至多一张有效单。
        Index(
            "uq_penetration_active_basin_no",
            "basin_id",
            "slip_no",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
            sqlite_where=text("voided_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    basin_id: Mapped[int] = mapped_column(ForeignKey("basins.id"))
    slip_no: Mapped[int] = mapped_column(Integer)
    vacuum: Mapped[float] = mapped_column(Float)
    penetrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    operator: Mapped[str] = mapped_column(String(64), default="")
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    basin: Mapped[Basin] = relationship(back_populates="tickets")
