from .base import Base
from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy.orm import backref, relationship
import base64
import logging
import json
import os
import uuid


__all__ = ['Workflow']


LOG = logging.getLogger(__name__)



def _generate_uuid():
    return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2]


class Workflow(Base):
    __tablename__ = 'workflow'

    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True, nullable=False,
            index=True,
            default=_generate_uuid)

    net_key = Column(Text, unique=True,
            index=True,
            default=_generate_uuid)

    root_task_id = Column(Integer, ForeignKey('task.id',
        use_alter=True, name='fk_workflow_root_task'))


    root_task = relationship('Task', post_update=True,
            foreign_keys=[root_task_id], lazy='joined')

    start_place_name = 'workflow-start-place'

    # This is the convention of the Petri service that the first token has
    # color 0 and parent_color None
    color = 0
    parent_color = None

    @property
    def links(self):
        results = []

        for name,task in self.tasks.iteritems():
            results.extend(task.input_links)

        return sorted(results,
                key=lambda l: l.source_task.name\
                    + l.destination_task.name\
                    + l.source_property\
                    + l.destination_property)
        return results

    @property
    def tasks(self):
        return self.root_task.method_list[0].children

    @property
    def status(self):
        return self.root_task.status(color=self.color)

    @property
    def executions(self):
        return self.root_task.method_list[0].executions


    @property
    def is_canceled(self):
        return self.root_task.is_canceled

    def cancel(self):
        if self.is_canceled:
            return
        else:
            for task in self.all_tasks:
                task.cancel()

    def get_webhooks(self, *args, **kwargs):
        return self.root_task.method_list[0].get_webhooks(*args, **kwargs)

    def as_dict(self, detailed):
        tasks = {name: task.as_dict(detailed=detailed)
            for name,task in self.tasks.iteritems()
                if name not in ['input connector', 'output connector']}
        links = [l.as_dict(detailed=detailed) for l in self.links]

        result = {
            'tasks': tasks,
            'links': links,
            'inputs': self.root_task.get_inputs(colors=[0], begins=[0]),
            'status': self.status,
            'name': self.name,
        }
        webhooks = self.get_webhooks()
        if webhooks:
            result['webhooks'] = webhooks

        return result

        if detailed:
            result['executions'] = {
                    color: execution.as_dict(detailed=detailed)
                    for color, execution in self.executions.iteritems()}

        return result

    def attach_expire_transition(self, transitions, pn, ttl):
        transitions.append({
                'inputs': [pn],
                'action': {
                    'type': 'expire',
                    'ttl_seconds': ttl
                }
            })

    def get_petri_transitions(self):
        transitions = []
        success_place, failure_place = self.root_task.attach_transitions(
                transitions, self.start_place_name)

        success_ttl = os.environ.get('PTERO_WORKFLOW_SUCCEEDED_EXPIRE_SECONDS')
        if success_ttl is not None:
            self.attach_expire_transition(transitions, success_place,
                    int(success_ttl))

        failure_ttl = os.environ.get('PTERO_WORKFLOW_FAILED_EXPIRE_SECONDS')
        if failure_ttl is not None:
            self.attach_expire_transition(transitions, failure_place,
                    int(failure_ttl))

        return transitions

    def get_outputs(self):
        return self.root_task.get_outputs(0)
