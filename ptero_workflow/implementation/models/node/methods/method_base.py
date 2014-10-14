from ...base import Base
from ...json_type import JSON
from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship
import os


__all__ = ['Method']


class Method(Base):
    __tablename__ = 'method'

    __table_args__ = (
        UniqueConstraint('node_id', 'name'),
    )

    id = Column(Integer, primary_key=True)

    node_id = Column(Integer, ForeignKey('node.id'))
    task = relationship('Node')

    name = Column(Text)

    index = Column(Integer, nullable=False, index=True)

    parameters = Column(JSON, nullable=False)

    service = Column(Text, nullable=False)
    __mapper_args__ = {
        'polymorphic_on': 'service',
    }

    VALID_CALLBACK_TYPES = set()

    def handle_callback(self, callback_type, body_data, query_string_data):
        if callback_type in self.VALID_CALLBACK_TYPES:
            return getattr(self, callback_type)(body_data, query_string_data)
        else:
            raise RuntimeError('Invalid callback type (%s).  Allowed types: %s'
                    % (callback_type, self.VALID_CALLBACK_TYPES))

    def callback_url(self, callback_type, **params):
        if params:
            query_string = '?%s' % urllib.urlencode(params)
        else:
            query_string = ''

        return 'http://%s:%d/v1/callbacks/methods/%d/callbacks/%s%s' % (
            os.environ.get('PTERO_WORKFLOW_HOST', 'localhost'),
            int(os.environ.get('PTERO_WORKFLOW_PORT', 80)),
            self.id,
            callback_type,
            query_string,
        )
