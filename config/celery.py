import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('lms')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'close-expired-quizzes-every-5-minutes': {
        'task': 'apps.assessments.tasks.close_expired_quizzes',
        'schedule': crontab(minute='*/5'),
    },
    'close-expired-assignments-every-5-minutes': {
        'task': 'apps.assessments.tasks.close_expired_assignments',
        'schedule': crontab(minute='*/5'),
    },
}
