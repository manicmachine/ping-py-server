import subprocess
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP
from typing import Dict, List, Tuple

from celery import chain, chord, shared_task
from flask import Flask, current_app

from ping.database_service import DatabaseService
from ping.models.monitor_device import MonitorDevice


class MonitorService:
    def __init__(self, database: DatabaseService):
        self.db = database

    def add_devices(self, devices: List[MonitorDevice]):
        self.db.create_devices(devices)

    def remove_devices(self, device_ids: List[int]):
        self.db.delete_devices(device_ids)
        
    def update_devices(self, devices: List[MonitorDevice]):
        self.db.update_devices(devices)
    
    def get_devices(self, device_ids: List[int] = None) -> Dict[int, MonitorDevice]:
        if not device_ids:
            return {device.id:device for device in self.db.get_all_devices()}
        else:
            return {device.id:device for device in self.db.read_devices(device_ids)}


def monitor_service_init_app(app: Flask, database: DatabaseService) -> MonitorService:
    monitor_service = MonitorService(database)
    app.extensions['monitor_service'] = monitor_service

    return monitor_service

@shared_task()
def cleanup_monitor(callback_args):
    # Due to Celery chords _requiring_ that the results of the chain be passed to the callback, we're defining 
    # an argument but explicitly ignoring it. 
    def should_cleanup(device: MonitorDevice) -> bool:
        return True if (device.been_notified and not device.persist) else False

    monitor_service = current_app.extensions['monitor_service']
    devices_pending_removal = [id for id,device in monitor_service.get_devices().items() if should_cleanup(device)]
    monitor_service.remove_devices(devices_pending_removal)
    
@shared_task()
def can_connect(device_id: int) -> Tuple[int, bool]:
    """Checks if the device associated with the provided ID can be connected to.
    Returns the device id along with the results of the connection test."""
    device = current_app.extensions['monitor_service'].get_devices().get(device_id)

    if not device:
        current_app.logger.error(f'Invalid device ID provided to check connecticity: {device_id}')
        raise ValueError(f'Invalid device ID provided to check connecticity: {device_id}')
        
    current_app.logger.info(f'[{device.name}] Checking connectivity')
    proc = None

    try:
        match device.port:
            case None:
                current_app.logger.debug(f'[{device.name}] Pinging address {device.identifier}')
                proc = subprocess.run(['/bin/ping', '-W', '1', '-c', '3', device.identifier], stdout=subprocess.DEVNULL)
            case "TCP":
                current_app.logger.debug(f'[{device.name}] Testing TCP port {device.port}')
                proc = subprocess.run(['/bin/nc', '-z', '-w', '1', device.identifier, device.port], stdout=subprocess.DEVNULL)
            case "UDP":
                current_app.logger.debug(f'[{device.name}] Testing UDP port {device.port}')
                proc = subprocess.run(['/bin/nc', '-z', '-w', '1', '-u', device.identifier, device.port], stdout=subprocess.DEVNULL)
            case _:
                raise ValueError('Invalid protocol provided')
    except Exception as e:
        current_app.logger.error(f'[{device.name}] Error encountered, {e}]')
        return device_id, None
    else:
        can_connect = True if proc.returncode == 0 else False
        current_app.logger.debug(f'[{device.name}] Can connect: {can_connect}')
        return device_id, can_connect

@shared_task()
def process_notification(device_and_connectivity: Tuple[int, bool]):
    def format_message(device: MonitorDevice, str_template: str) -> str:
        template_mappings = {
            '$name': f'{device.name}',
            '$identifier': f'{device.identifier}',
            '$port': f'{device.port}',
            '$protocol': f'{device.proto}',
            '$trigger': f'{device.monitor_trigger}',
            '$requested_by': f'{device.requested_by}',
            '$comments': f'{device.comments}'
        }

        formatted_message = str_template
        for mapping, value in template_mappings.items():
            formatted_message = formatted_message.replace(mapping, value)
        
        return formatted_message
    
    device_id, can_connect  = device_and_connectivity
    device = current_app.extensions['monitor_service'].get_devices().get(device_id)

    if can_connect == None:
        current_app.logger.error(f'Process notification invoked without connection information: {device.name}')
        raise ValueError(f'Process notification invoked without connection information: {device.name}')

    '''Since we're comparing a time range for any given day, and not a specific day, we need a hacky workaround to
    simplify the comparison. Since datetime comparisons are typically done using epoch, this approach won't work as that
    is a specific point in time. Instead, here we're turning the current hour and minute into an integer, same for the
    start and end windows for notifications, and doing a straight integer comparison. Janky, but it works. Note the 
    trigger times are in 24h format'''

    current_time_utc = (datetime.now(UTC).hour * 100) + datetime.now(UTC).minute
    trigger_start_utc = int(device.monitor_start_utc.replace(':',''))
    trigger_end_utc = int(device.monitor_end_utc.replace(':',''))

    current_app.logger.info(f'[{device.name}] Processing notification trigger criteria')
    current_app.logger.debug(f'Criteria: {{"identifier": {device.identifier}, "trigger": {device.monitor_trigger}, "port": {device.port}, "proto": {device.proto}}}')
    if current_time_utc >= trigger_start_utc and current_time_utc <= trigger_end_utc:
        if ((can_connect and device.monitor_trigger == 'ONLINE') or (not can_connect and device.monitor_trigger == 'OFFLINE')) and not device.been_notified:
            current_app.logger.info(f'[{device.name}] Notification trigger criteria met. Sending notifications to: {device.notify}')
            
            email_subject_text = f'[Ping] {format_message(device, device.email_subject)}'
            email_body_text = format_message(device, device.email_body)
        elif device.persist and ((can_connect and device.monitor_trigger == 'OFFLINE') or (not can_connect and device.monitor_trigger == 'ONLINE')) and device.been_notified:
            # Persisted records should also send notifications when they change back to the other state, i.e. a service that was offline is now back online
            current_app.logger.info(f'Notification trigger criteria met for persisted record {device.name}. Sending notifications to: {device.notify}')

            email_subject_text = f'[Ping] {device.name} is now {'ONLINE' if can_connect else 'OFFLINE'}'
            email_body_text = f'{device.name} is now back {'ONLINE' if can_connect else 'OFFLINE'}.'
        else:
            current_app.logger.info(f'[{device.name}] Notification trigger criteria not met')
            return

        sender_email = current_app.config['SENDER_EMAIL']
        reply_to_email = current_app.config['REPLY_TO_EMAIL']
        email_body = MIMEText(email_body_text, 'plain')
        msg = MIMEMultipart('alternative')
        msg['To'] = device.notify
        msg['From'] = sender_email
        msg['reply-to'] = reply_to_email
        msg['Subject'] = email_subject_text
        msg.attach(email_body)

        try:
            smtp_server = SMTP(current_app.config['SMTP_SERVER'])
            smtp_server.send_message(msg)
            current_app.logger.info(f'[{device.name}] Notification email sent')
        except Exception as e:
            current_app.logger.error(f'[{device.name}] Error sending notifications. {e}')
        else:
            if device.persist and device.been_notified:
                # Reset the notification flag for persistant records
                device.been_notified = False
            else:
                device.been_notified = True

            current_app.extensions['monitor_service'].update_devices([device])
        finally:
            smtp_server.quit()
    else:
        current_app.logger.info(f'[{device.name}] Outside notification window of {device.monitor_start_utc} and {device.monitor_end_utc} UTC')

@shared_task()
def monitor_run():
    monitor_list = current_app.extensions['monitor_service'].get_devices()
    current_app.logger.info(f'Starting monitor run. {len(monitor_list)} in queue.')

    task_chain = [chain(can_connect.s(id), process_notification.s()) for id in monitor_list]
    callback = cleanup_monitor.s()
    monitor_task_chord = chord(task_chain)(callback)
