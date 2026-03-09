"""Pytest configuration and fixtures for Second Brain tests."""

import pytest
from second_brain import config


@pytest.fixture(autouse=True)
def restore_config_after_test():
    """Automatically restore config.BRAIN_DIR after each test.

    This ensures that even if a test fails or doesn't properly restore
    the config in its finally block, the global state is cleaned up.
    """
    # Store original values
    original_brain_dir = config.BRAIN_DIR
    original_dump_file = config.DUMP_FILE
    original_todo_file = config.TODO_FILE

    yield

    # Restore original values after test completes
    config.BRAIN_DIR = original_brain_dir
    config.DUMP_FILE = original_dump_file
    config.TODO_FILE = original_todo_file
    config.reload_config()
