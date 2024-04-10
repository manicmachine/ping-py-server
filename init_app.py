import json
from datetime import timedelta
from ping import create_app

flask_app = create_app()
celery_app = flask_app.extensions['celery']

celery_app.conf.beat_schedule = {
    'monitor-run-every-minute': {
        'task': 'ping.monitor_service.monitor_run',
        'schedule': timedelta(minutes=1)
    }
}