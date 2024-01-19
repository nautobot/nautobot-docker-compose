"""Nautobot plugin for example."""
__version__ = "0.1.0"

from nautobot.extras.plugins import PluginConfig
from health_check.plugins import plugin_dir
from .healthcheck import ExampleCheckBackend


class ExampleConfig(PluginConfig):
    """Plugin configuration for the nautobot_example plugin."""

    name = "nautobot_example_plugin"
    verbose_name = "Simple project for example"
    version = "0.1.1"
    author = "Network to Code"
    description = ""
    base_url = "example"
    required_settings = []
    default_settings = {}
    caching_config = {}

    def ready(self):
        """Adds the example Heath Check Backend to the health check registry."""
        super().ready()
        plugin_dir.register(ExampleCheckBackend)


config = ExampleConfig  # pylint: disable=invalid-name
