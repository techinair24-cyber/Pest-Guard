import os

class SmsNotConfiguredError(RuntimeError):
    pass


def send_sms_alert(detection: dict):
    api_key = os.getenv('SMS_API_KEY')
    api_secret = os.getenv('SMS_API_SECRET')
    alert_phone = os.getenv('ALERT_PHONE_NUMBER')
    sms_url = os.getenv('SMS_API_URL')
    if not all((api_key, api_secret, alert_phone, sms_url)):
        raise SmsNotConfiguredError('SMS provider is not configured')
    # Provider-specific HTTP integration belongs here. Credentials are never hardcoded.
    return {'sent': False, 'reason': 'SMS provider adapter not implemented'}
