from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.models import EventKind, EventStatus


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    # Telegram user id
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    timezone: Mapped[str] = mapped_column(String(64))
    voice_replies: Mapped[bool] = mapped_column(Boolean, server_default=true())
    digest_time: Mapped[time | None] = mapped_column(Time)
    last_digest_on: Mapped[date | None] = mapped_column(Date)
    ics_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    meeting_lead_minutes: Mapped[int] = mapped_column(Integer, server_default="15")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default=EventStatus.OPEN.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recurrence: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(16))  # 'demo' — данные из тестового задания

    __table_args__ = (Index("ix_events_user_starts_at", "user_id", "starts_at"),)

    def to_domain(self):
        from app.core.models import Event

        return Event(
            id=self.id,
            user_id=self.user_id,
            kind=EventKind(self.kind),
            title=self.title,
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            all_day=self.all_day,
            status=EventStatus(self.status),
            created_at=self.created_at,
            notified_at=self.notified_at,
            recurrence=self.recurrence,
        )
