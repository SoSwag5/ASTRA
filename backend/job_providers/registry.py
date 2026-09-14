"""Provider lookup by name. Adding a provider means adding one entry here,
never an if/elif chain in core business logic.
"""
from .ashby import AshbyProvider
from .greenhouse import GreenhouseProvider
from .lever import LeverProvider

_PROVIDERS = {
    'greenhouse': GreenhouseProvider(),
    'lever': LeverProvider(),
    'ashby': AshbyProvider(),
}


def get_provider(name):
    return _PROVIDERS.get(name)
