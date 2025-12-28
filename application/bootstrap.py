
from application.di import DIContainer


def BootstrapApplication():
    print("Bootstrapping the application...")
    diContainer = DIContainer()
    diContainer.infrastructure_container
    diContainer.domain_container
    diContainer.interface_container
    # Add bootstrapping logic here
