from datetime import UTC, datetime, timedelta
from typing import Optional, Tuple

import jwt
from flask import current_app
from passlib.hash import argon2

from ping.database_service import DatabaseService
from ping.models.user import User


class AuthService():
    token_duration_min = 30

    def __init__(self, database_service: DatabaseService):
        self.database_service = database_service

    def verify_user(self, username: str, password: str) -> Optional[User]:
        # Check if local user
        user = self.database_service.read_user(username)

        if argon2.verify(password, user.secret):
            return user
        
        # Else, check if LDAP user
        return None
        # TODO: Implement LDAP auth

    def encode_auth_token(self, user: User) -> Tuple[str , datetime]:
        expires = datetime.now(UTC) + timedelta(minutes=self.token_duration_min)
        payload = {
            'exp': int(expires.timestamp()),
            'sub': user.username
        }

        return (jwt.encode(
            payload,
            current_app.config.get('SECRET_KEY'),
            algorithm='HS256'
        ), payload['exp'])

    @staticmethod
    def decode_auth_token(token: str) -> dict:
        payload = jwt.decode(token, current_app.config.get('SECRET_KEY'), algorithms=['HS256'])
        return payload