from enum import Enum


class MonitorTrigger(str, Enum):
    ONLINE = 'ONLINE'
    OFFLINE = 'OFFLINE'