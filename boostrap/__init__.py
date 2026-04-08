import importlib

BootstrapApplication = importlib.import_module("boostrap.bootstrap").BootstrapApplication
DIContainer = importlib.import_module("boostrap.di").DIContainer
ConsoleBootstrapApplication = importlib.import_module("boostrap.console_boostrap").ConsoleBootstrapApplication