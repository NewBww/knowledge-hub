"""Local, human-enabled external-agent handoff. No provider configuration."""
import json
from .core import DomainError
from .intake import private_write, data_lock

LIMITATION = 'An external harness may forward data after reading. Knowledge Hub does not control its models, credentials, downstream routing, training or retention.'


class AgentAccess:
    def __init__(self, store):
        self.store = store
        self.path = store.path.parent / 'capture-agent-access.json'

    def _project(self, project_id):
        if not any(project['id'] == project_id for project in self.store.projects()):
            raise DomainError('project_not_found', 404)

    def _load(self):
        if self.path.is_symlink():
            raise DomainError('unsafe_local_storage')
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or any(type(value) is not bool for value in data.values()):
                raise ValueError()
            return data
        except (ValueError, OSError):
            raise DomainError('invalid_agent_access_configuration') from None

    def get(self, project_id):
        self._project(project_id)
        with data_lock(self.store.path.parent):
            return {'agent_access': self._load().get(project_id, False), 'limitation': LIMITATION}

    def set(self, project_id, enabled):
        self._project(project_id)
        if type(enabled) is not bool:
            raise DomainError('invalid_agent_access', 422)
        with data_lock(self.store.path.parent):
            data = self._load()
            data[project_id] = enabled
            private_write(self.path, json.dumps(data).encode())
            return self.get(project_id)

    def require(self, project_id):
        if not self.get(project_id)['agent_access']:
            raise DomainError('agent_access_disabled', 403)
