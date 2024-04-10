from typing import List

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import delete, update

from ping.models.base import Base
from ping.models.monitor_device import MonitorDevice
from ping.models.user import User


class DatabaseService():

    def __init__(self, app):
        self.app = app
        self.database = SQLAlchemy(model_class=Base)
        app.extensions['database_service'] = self
    
    def init_app(self):
        self.database.init_app(self.app)

        with self.app.app_context():
            self.database.create_all()
    
    def get_all_devices(self) -> List[MonitorDevice]:
        with self.app.app_context():
            return self.database.session.query(MonitorDevice).all()

    def create_devices(self, devices: List[MonitorDevice]):
        with self.app.app_context():
            self.database.session.add_all(devices)
            self.database.session.commit()

    def read_devices(self, device_ids: List[MonitorDevice]) -> List[MonitorDevice]:
        with self.app.app_context():
            return self.database.session.query(MonitorDevice).where(MonitorDevice.id.in_(device_ids)).all()

    def update_devices(self, devices: List[dict]):
        with self.app.app_context():
            for device in devices:
                if isinstance(device, MonitorDevice):
                    # Handle updating device internally
                    self.database.session.merge(device)
                else:
                    # Handle updating device with partial JSON via API
                    statement = (
                        update(MonitorDevice)
                        .where(MonitorDevice.id == device['id'])
                        .values(device)
                    )

                    self.database.session.execute(statement)

            self.database.session.commit()

    def delete_devices(self, device_ids: List[int]):
        with self.app.app_context():
            self.database.session.execute(delete(MonitorDevice).where(MonitorDevice.id.in_(device_ids)))
            self.database.session.commit()

    def create_user(self, user: User):
        with self.app.app_context():
            self.database.session.add(user)
            self.database.session.commit()

    def read_user(self, username: str) -> User:
        with self.app.app_context():
            return self.database.session.query(User).where(User.username == username).one()