from . import models
from .models.execution.execution_base import Execution
from . import tasks
from . import translator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from ptero_workflow.implementation import exceptions
import os
import logging

LOG = logging.getLogger(__name__)


_TASK_BASE = 'ptero_workflow.implementation.celery_tasks.'


class Backend(object):
    def __init__(self, session, celery_app):
        self.session = session
        self.celery_app = celery_app

    @property
    def submit_net_task(self):
        return self.celery_app.tasks[_TASK_BASE + 'submit_net.SubmitNet']

    @property
    def http_task(self):
        return self.celery_app.tasks['ptero_common.celery.http.HTTP']

    def create_workflow(self, workflow_data):
        try:
            workflow = self._save_workflow(workflow_data)
        except IntegrityError as e:
            sqlite_error = 'UNIQUE constraint failed: workflow.name'
            postgres_error = 'duplicate key value violates unique constraint "workflow_name_key"'
            if e.orig.message == sqlite_error or e.orig.message.startswith(postgres_error):
                raise exceptions.InvalidWorkflow(
                    "Workflow with name '%s' already exists" % workflow_data['name'])
            else:
                raise exceptions.InvalidWorkflow('Unknown IntegrityError: %s' % e.message)
        self.submit_net_task.delay(workflow.id)
        return workflow.id, workflow.as_dict(detailed=False)

    def submit_net(self, workflow_id):
        workflow = self.session.query(models.Workflow).get(workflow_id)
        petri_data = translator.build_petri_net(workflow)
        self.http_task.delay('PUT', self._petri_submit_url(workflow.net_key), **petri_data)

    def _petri_submit_url(self, net_key):
        return 'http://%s:%d/v1/nets/%s' % (
            os.environ.get('PTERO_PETRI_HOST', 'localhost'),
            int(os.environ.get('PTERO_PETRI_PORT', 80)),
            net_key,
        )

    def _save_workflow(self, workflow_data):
        workflow = models.Workflow(name=workflow_data.get('name'))

        root_data = {
            'methods': [
                {
                    'name': 'root',
                    'parameters': {
                        'tasks': workflow_data['tasks'],
                        'links': workflow_data['links'],
                        'webhooks': workflow_data.get('webhooks', {}),
                    },
                    'service': 'workflow',
                },
            ],
        }

        workflow.root_task = tasks.build_task('root', root_data)
        models.TaskExecution(task=workflow.root_task, color=0, parent_color=None,
                colors=[0], begins=[], data={})

        tasks.create_input_holder(workflow.root_task, workflow_data['inputs'],
                color=workflow.color, parent_color=workflow.parent_color)

        dummy_output_task = models.InputHolder(name='dummy output task')
        self.session.add(dummy_output_task)

        for link_data in workflow_data['links']:
            if 'output connector' == link_data['destination']:
                self.session.add(models.Link(source_task=workflow.root_task,
                        source_property=link_data['destinationProperty'],
                        destination_task=dummy_output_task,
                        destination_property=link_data['destinationProperty']))

        self.session.add(workflow)
        self.session.commit()

        workflow.root_task.create_input_sources(self.session, [])

        self.session.commit()

        return workflow

    def _get_workflow(self, workflow_id):
        workflow = self.session.query(models.Workflow).get(workflow_id)
        if workflow is not None:
            return workflow
        else:
            raise exceptions.NoSuchEntityError(
                    "Workflow with id %s was not found." % workflow_id)

    def get_workflow(self, workflow_id):
        return self._get_workflow(workflow_id).as_dict(detailed=False)

    def get_workflow_by_name(self, workflow_name):
        try:
            workflow = self.session.query(models.Workflow).filter_by(
                name=workflow_name).one()
            return workflow.id, workflow.as_dict(detailed=False)
        except NoResultFound:
            raise exceptions.NoSuchEntityError(
                    "Workflow with name %s was not found." % workflow_name)

    def cancel_workflow(self, workflow_id):
        self._get_workflow(workflow_id).cancel()
        self.session.commit()

    def get_workflow_status(self, workflow_id):
        return self._get_workflow(workflow_id).status

    def get_workflow_details(self, workflow_id):
        return self._get_workflow(workflow_id).as_dict(detailed=True)

    def get_workflow_outputs(self, workflow_id):
        return self._get_workflow(workflow_id).get_outputs()

    def _get_execution(self, execution_id):
        execution = self.session.query(Execution).get(execution_id)
        if execution is not None:
            return execution
        else:
            raise exceptions.NoSuchEntityError(
                    "Execution with id %s was not found." % execution_id)

    def get_execution(self, execution_id):
        return self._get_execution(execution_id).as_dict(detailed=False)

    def update_execution(self, execution_id, update_data):
        execution = self._get_execution(execution_id)
        execution.update(update_data)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise exceptions.OutputsAlreadySet
        return execution.as_dict(detailed=False)

    def handle_task_callback(self, task_id, callback_type, body_data,
            query_string_data):
        task = self.session.query(models.Task
                ).filter_by(id=task_id).one()
        task.handle_callback(callback_type, body_data, query_string_data)

    def handle_method_callback(self, method_id, callback_type, body_data,
            query_string_data):
        method = self.session.query(models.Method
                ).filter_by(id=method_id).one()
        method.handle_callback(callback_type, body_data, query_string_data)

    def cleanup(self):
        self.session.rollback()
