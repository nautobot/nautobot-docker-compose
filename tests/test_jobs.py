"""Tests module."""

from unittest import TestCase

from nautobot.apps.testing import (
    TransactionTestCase,
    create_job_result_and_run_job,
)

class FirstTest(TestCase):
    """First test case."""

    def test_first(self):
        """First test."""
        self.assertEqual(1, 1)

class RunJobTestCase(TransactionTestCase):
    """Test Class."""

    def setUp(self) -> None:
        """Run setup tasks."""
        super().setUp()

    def test_job(self):
        """Verify Job runs successfully."""
        job_result = create_job_result_and_run_job(
            module="initial_data",
            name="InitialDesign",
            dryrun=False,
        )
        self.assertEqual("SUCCESS", job_result.status, job_result.traceback)