import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('mtg_tracker')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Windows compatibility: use threads pool for parallelism without prefork issues
if os.name == 'nt':  # Windows
    app.conf.worker_pool = 'threads'
    app.conf.worker_prefetch_multiplier = 1
    app.conf.worker_max_tasks_per_child = 1000

app.autodiscover_tasks()
