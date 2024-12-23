import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'city_wiki.settings')

app = Celery('city_wiki')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks() 