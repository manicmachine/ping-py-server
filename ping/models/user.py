from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ping.models.base import Base


class User(Base):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(30), primary_key=True)
    secret: Mapped[str] = mapped_column(Text)