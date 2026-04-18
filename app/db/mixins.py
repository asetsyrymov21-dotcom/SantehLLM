import datetime as dt
from typing import Annotated

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


TimestampUTC = Annotated[dt.datetime, mapped_column(DateTime(timezone=True))]


class TimestampMixin:
    created_at: Mapped[TimestampUTC] = mapped_column(
        default=func.now(), nullable=False
    )
    updated_at: Mapped[TimestampUTC] = mapped_column(
        default=func.now(), onupdate=func.now(), nullable=False
    )


class CreatedAtMixin:
    created_at: Mapped[TimestampUTC] = mapped_column(
        default=func.now(), nullable=False
    )
