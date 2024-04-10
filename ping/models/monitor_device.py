from json import JSONEncoder
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ping.models.base import Base
from ping.models.monitor_trigger import MonitorTrigger


class MonitorDevice(Base):
    __tablename__ = "monitor_device"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    identifier: Mapped[str] = mapped_column(String(50))
    port: Mapped[Optional[int]] = mapped_column(Integer)
    proto: Mapped[Optional[str]] = mapped_column(String(3)) # TODO: Change this to an ENUM to validate supported protocols are provided
    persist: Mapped[bool] = mapped_column(Boolean)
    monitor_trigger: Mapped[str] = mapped_column(String(10), default=MonitorTrigger.OFFLINE.value)
    monitor_start_utc: Mapped[str] = mapped_column(String(5))
    monitor_end_utc: Mapped[str] = mapped_column(String(5))
    requested_by: Mapped[str] = mapped_column(String(50))
    notify: Mapped[str] = mapped_column(Text)
    comments: Mapped[Optional[str]] = mapped_column(Text)
    email_subject: Mapped[str] = mapped_column(String(70))
    email_body: Mapped[str] = mapped_column(Text)
    been_notified: Mapped[bool] = mapped_column(Boolean, default=False)


class MonitorDeviceEncoder(JSONEncoder):
    encodable_vals = [
        'id',
        'name',
        'identifier',
        'port',
        'proto',
        'persist',
        'monitor_trigger',
        'monitor_start_utc',
        'monitor_end_utc',
        'requested_by',
        'notify',
        'comments',
        'email_subject',
        'email_body']
    
    def default(self, obj):
        if isinstance(obj, MonitorDevice):
            dict = {}
            for val in self.encodable_vals:
                dict[val] = getattr(obj, val)
            
            return dict