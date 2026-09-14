"""Provider lookup by name. Adding a provider means adding one entry here,
never an if/elif chain in core business logic.
"""
from .greenhouse import GreenhouseProvider

_PROVIDERS = {
    'greenhouse': GreenhouseProvider(),
}


def get_provider(name):
    return _PROVIDERS.get(name)
