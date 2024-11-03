import pytest
import sentry_sdk

from app.app import Core


class BaseTestCase(TestCase):
    """A base test case."""

    @pytest.fixture
    def client(self):
        """[summary]

        Yields:
            [type]: [description]
        """

    def create_app(self):

    def setUp(self):
        """For future use"""

    def tearDown(self):
        """For future use."""
