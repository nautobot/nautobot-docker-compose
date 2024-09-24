"""Initial data required for core sites."""
from nautobot.apps.jobs import register_jobs

from nautobot_design_builder.design_job import DesignJob

from .context import InitialDesignContext


class InitialDesign(DesignJob):
    """Initialize the database with default values needed by the core site designs."""
    has_sensitive_variables = False

    class Meta:
        """Metadata needed to implement the backbone site design."""

        name = "Initial Data"
        commit_default = False
        design_file = "designs/0001_design.yaml.j2"
        context_class = InitialDesignContext

name = "Demo Designs"
register_jobs(InitialDesign)