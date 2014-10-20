from .base import Base
from sqlalchemy import Column, UniqueConstraint
from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import backref, relationship
from sqlalchemy.orm.session import object_session
import json_type
import logging
import os
import simplejson


__all__ = ['Result']


LOG = logging.getLogger(__file__)


class Result(Base):
    __tablename__ = 'result'
    __table_args__ = (
        UniqueConstraint('task_id', 'name', 'color'),
    )

    id           = Column(Integer, primary_key=True)

    task_id = Column(Integer, ForeignKey('task.id'), nullable=True)
    name    = Column(Text, nullable=False, index=True)
    color   = Column(Integer, nullable=False, index=True)
    parent_color = Column(Integer, nullable=True, index=True)

    type         = Column(Text, nullable=False)

    task = relationship('Task', backref='results')

    __mapper_args__ = {
        'polymorphic_on': 'type',
    }


class ConcreteResult(Result):
    __tablename__ = 'result_concrete'

    id = Column(Integer, ForeignKey('result.id'), primary_key=True)

    data = Column(json_type.JSON)

    __mapper_args__ = {
        'polymorphic_identity': 'concrete'
    }

    @property
    def size(self):
        return json_type.get_data_size(self)

    def get_element(self, index):
        return json_type.get_data_element(self, index)
