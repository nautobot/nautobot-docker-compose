"""The __init__.py module is required for Nautobot to load the jobs via Git."""

from .initial_data import InitialDesign

__all__ = [
    "InitialDesign",
]