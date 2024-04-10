from datetime import UTC, datetime
from functools import wraps

import jwt
from flask import current_app, request
from jwt import DecodeError, ExpiredSignatureError


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' not in request.headers:
            return '', 401

        auth_data = request.headers['Authorization'].split()

        if auth_data[0] != 'Bearer':
            return '', 401
        else:
            token = auth_data[1]

        if not token:
            current_app.logger.info(f'Unauthorized {request.method} request made from {request.remote_addr} to {request.path}')
            return '', 401
        
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            if data['exp'] <= int(datetime.now(UTC).timestamp()) or current_app.config['REVOKED_TOKENS'].get(token):
                return '', 401
            
        except DecodeError as e:
            current_app.logger.error(f'Invalid token sent while making {request.method} request from {request.remote_addr} to {request.path}')
            return '', 400
        except ExpiredSignatureError as e:
            current_app.logger.error(f'Expired token sent while making {request.method} request from {request.remote_addr} to {request.path}')
            return '', 401
        except Exception as e:
            current_app.logger.error(f'Exception thrown while validating token: {e}')
            return '', 500
        
        return f(*args, **kwargs)

    return decorated