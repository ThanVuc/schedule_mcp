
from infrastructure.container import InfrastructureContainer


class DomainContainer:
    def __init__(self, infrastructure: InfrastructureContainer):
        # Keep a reference for domain services to use shared infrastructure
        self.infrastructure = infrastructure
