import sys

import pytest
from loguru import logger

from papersys.cli import main


def test_cli_serve_dry_run(capsys, tmp_path):
    """Test the 'serve --dry-run' command."""
    # Reconfigure logger to ensure capture by capsys
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Create a dummy config file
    config_content = """
[scheduler]
enabled = true

[scheduler.recommend_job]
enabled = true
name = "test-recommend"
cron_schedule = "* * * * *"

[scheduler.summary_job]
enabled = true
name = "test-summary"
cron_schedule = "* * * * *"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    # Run the CLI command with corrected argument order
    return_code = main(["--config", str(config_file), "serve", "--dry-run"])

    assert return_code == 0

    # Check the output
    captured = capsys.readouterr()
    assert "Setting up scheduled jobs..." in captured.err
    assert "Registering job 'recommend'" in captured.err
    assert "Registering job 'summary'" in captured.err
    assert "[Dry Run] Jobs have been validated and registered." in captured.err
    assert "[Dry Run] Server will not be started." in captured.err