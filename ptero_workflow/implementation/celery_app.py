from celery.signals import worker_process_init, setup_logging
import celery
import os
import time
from factory import Factory
from ptero_common.logging_configuration import configure_celery_logging


app = celery.Celery('PTero-workflow-celery',
        include='ptero_workflow.implementation.celery_tasks')

app.conf['CELERY_ROUTES'] = (
    {
        'ptero_workflow.implementation.celery_tasks.submit_net.SubmitNet': {'queue': 'submit'},
        'ptero_common.celery.http.HTTP': {'queue': 'http'},
        'ptero_common.celery.http.HTTPWithResult': {'queue': 'http'},
    },
)

_DEFAULT_CELERY_CONFIG = {
    'CELERY_BROKER_URL': 'amqp://localhost',
    'CELERY_RESULT_BACKEND': 'redis://localhost',
    'CELERY_ACCEPT_CONTENT': ['json'],
    'CELERY_ACKS_LATE': True,
    'CELERY_RESULT_SERIALIZER': 'json',
    'CELERY_TASK_SERIALIZER': 'json',
    'CELERYD_PREFETCH_MULTIPLIER': 10,
}
for var, default in _DEFAULT_CELERY_CONFIG.iteritems():
    if var in os.environ:
        app.conf[var] = os.environ[var]
    else:
        app.conf[var] = default

# This has to be imported AFTER the app.conf is set up or
# the tasks will default to using pickle serialization which is forbidden by
# this configuration.
from . import celery_tasks


@setup_logging.connect
def setup_celery_logging(**kwargs):
    configure_celery_logging("WORKFLOW")


@worker_process_init.connect
def initialize_factory(**kwargs):
    app.factory = Factory(
        connection_string=os.environ.get('PTERO_WORKFLOW_DB_STRING',
            'sqlite://'), celery_app=app)
