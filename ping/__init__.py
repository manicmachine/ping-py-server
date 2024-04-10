import base64
import json
import os
from datetime import UTC, datetime

import click
from flask import Flask, Response, request
from jwt import DecodeError
from passlib.hash import argon2

from ping.auth_middleware import token_required
from ping.auth_service import AuthService
from ping.config import *
from ping.database_service import DatabaseService
from ping.models.monitor_device import MonitorDevice, MonitorDeviceEncoder
from ping.models.user import User
from ping.monitor_service import monitor_service_init_app
from ping.task_queue import celery_init_app


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        REVOKED_TOKENS={},
        CELERY=dict(
            broker_url='redis://broker:6379/0',
            result_backend='redis://broker:6379/0',
        )
    )

    # Load environment variables into configuration, loads all environment variables starting with FLASK_
    app.config.from_prefixed_env()

    if test_config is None:
        if app.config['DEBUG']:
            app.config.from_object(DevelopmentConfig)
        elif app.config['TESTING']:
            app.config.from_object(TestingConfig)
        else:
            app.config.from_object(ProductionConfig)
    else:
        # load the test config if passed in
        app.config.from_pyfile(test_config)

    # ensure the instance folder exists
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)

    # Initialize services
    task_queue = celery_init_app(app)
    database_service = DatabaseService(app)
    database_service.init_app()
    monitor_service = monitor_service_init_app(app, database_service)
    auth_service = AuthService(database_service)

    # Configure CLI
    @click.command('add-local-user')
    @click.argument('username')
    @click.password_option(help='The password for the new user')
    def add_local_user(username, password):
        database_service.create_user(User(username=username, secret=argon2.hash(password)))

    app.cli.add_command(add_local_user)

    # Configure routes
    @app.route('/')
    def index():
        # TODO: Wire up front-end
        return '', 200

    @app.route('/api/token', methods=['POST', 'DELETE'])
    def process_token_req():
        """Either returns a new auth token or invalids the provided one"""

        auth_data = None
        if 'Authorization' not in request.headers:
            return '', 401
        else:
            auth_data = request.headers['Authorization'].split()

        if request.method == 'POST':
            if auth_data[0] != 'Basic':
                return '', 400

            (username, password) = base64.b64decode(auth_data[1]).decode('utf-8').split(':')
            user = auth_service.verify_user(username=username, password=password)

            if user:
                try:
                    (token, exp) = auth_service.encode_auth_token(user)
                except Exception as e:
                    app.logger.error(f'Exception thrown while encoding auth token: {e}')
                    return '', 500

                return Response(json.dumps({'token': token, 'expires': exp}), status=200, mimetype='application/json')
            else:
                return '', 401
        elif request.method == 'DELETE':
            if auth_data[0] != 'Bearer':
                return '', 400
            
            token = auth_data[1]

            try:
                data = auth_service.decode_auth_token(token)
                if data['exp'] > int(datetime.now(UTC).timestamp()):
                    app.config['REVOKED_TOKENS'][token] = data['exp']
                
                return '', 200
            except DecodeError as e:
                app.logger.error(f'Invalid token sent while making {request.method} request from {request.remote_addr} to {request.path}')
                return '', 400
            except Exception as e:
                app.logger.error(f'Exception thrown while revoking auth token: {e}')
                return '', 500

    @app.route('/api/monitoring', methods=['GET'])
    @token_required
    def process_monitoring_req():
        """Returns the current monitor list"""
        try:
            app.logger.info(f'Retrieving current monitor list for {request.remote_addr}')
            results = [device for device in monitor_service.get_devices().values()]
        except Exception as e:
            app.logger.error(f'Exception thrown while retrieving current monitor list: {e}')
            return '', 500
        else:
            return Response(json.dumps(results, cls=MonitorDeviceEncoder), status=200, mimetype='application/json')

    @app.route('/api/devices', methods=['GET', 'DELETE', 'PUT', 'POST'])
    @token_required
    def process_devices_req():
        """Process CRUD requests for devices"""
        app.logger.info(f'Processing {request.method} device request from {request.remote_addr}')
        req_json = request.get_json()
        if not req_json:
            return '', 400

        if request.method == 'GET':
            try:
                app.logger.info(f'Attempting to retrieve detailed monitor device records for device ids: {req_json}')
                results = [device for _, device in monitor_service.get_devices(req_json).items()]
            except Exception as e:
                app.logger.error(f'Exception thrown while retrieving current monitor list: {e}')
                return '', 500
            else:
                return Response(json.dumps(results, cls=MonitorDeviceEncoder), status=200, mimetype='application/json')
        elif request.method == 'POST':
            try:
                device_objects = []
                for device in req_json:
                    app.logger.info(f'Attempting to create monitor device record for: {device}')
                    device_objects.append(MonitorDevice(**device))

                monitor_service.add_devices(device_objects)
            except Exception as e:
                app.logger.error(f'Exception thrown while creating monitor devices: {e}')

                return '', 400
            else:
                return '', 201
        elif request.method == 'DELETE':
            app.logger.info(f'Attempting to delete the following records: {req_json}')

            database_service.delete_devices(req_json)
            monitor_service.remove_devices(req_json)

            return '', 204
        elif request.method == 'PUT':
            try:
                app.logger.info(f'Attempting to make the following updates: {req_json}')
                database_service.update_devices(req_json)
                monitor_service.update_devices(req_json)
            except Exception as e:
                app.logger.error(f'Exception thrown while updating monitor devices: {e}')

                return '', 400
            else:
                return '', 200

    return app