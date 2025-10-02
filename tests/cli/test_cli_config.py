import json
import sys
from contextlib import contextmanager

from loguru import logger

from papersys.cli import main


@contextmanager
def _logger_to_stderr():
    logger_id = logger.add(sys.stderr, level="INFO")
    try:
        yield
    finally:
        logger.remove(logger_id)


def test_config_check_json_success(capsys, tmp_path):
    config_text = """
[scheduler]
enabled = true
timezone = "UTC"

[summary_pipeline.pdf]
output_dir = "./pdfs"
model = "deepseek-r1"
language = "en"

enable_latex = false

[[llms]]
alias = "deepseek-r1"
name = "deepseek"
base_url = "https://example.com"
api_key = "env:DEEPSEEK_API_KEY"
temperature = 0.1
top_p = 0.9
num_workers = 1
native_json_schema = false
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_text)

    with _logger_to_stderr():
        exit_code = main(["--config", str(config_file), "config", "check", "--format", "json"])

    assert exit_code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert payload["warnings"] == []
    assert payload["config_path"].endswith("config.toml")


def test_config_check_missing_file(capsys, tmp_path):
    missing_path = tmp_path / "absent.toml"

    with _logger_to_stderr():
        exit_code = main(["--config", str(missing_path), "config", "check"])

    assert exit_code == 2

    captured = capsys.readouterr()
    assert "Configuration error (missing_file" in captured.err
    assert str(missing_path) in captured.err


def test_config_check_validation_error(capsys, tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("unknown_field = 42\n")

    with _logger_to_stderr():
        exit_code = main(["--config", str(config_file), "config", "check"])

    assert exit_code == 3

    captured = capsys.readouterr()
    assert "validation_error" in captured.err
    assert "Extra inputs are not permitted" in captured.err


def test_config_explain_text_output(capsys):
    with _logger_to_stderr():
        exit_code = main(["config", "explain"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Configuration schema" in captured.err
    assert "summary_pipeline.pdf.model" in captured.err
    assert "llms[].alias" in captured.err
