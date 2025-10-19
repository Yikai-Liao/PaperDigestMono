from papersys.cli import main

from .utils import logger_to_stderr


def _write_minimal_config(tmp_path):
    config_text = """
[scheduler]
enabled = true
timezone = "UTC"

[ingestion]
enabled = true
output_dir = "metadata/raw"

[embedding]
enabled = true
output_dir = "embeddings"

[[embedding.models]]
alias = "test"
name = "sentence-transformer/test"
dimension = 384
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_text)
    return config_file


def test_status_dry_run_reports_sections(capsys, tmp_path):
    config_file = _write_minimal_config(tmp_path)

    with logger_to_stderr():
        exit_code = main(["--config", str(config_file), "status", "--dry-run"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "=== General Configuration ===" in captured.err
    assert "=== Ingestion Configuration ===" in captured.err
    assert "=== Embedding Configuration ===" in captured.err
    assert "test: sentence-transformer/test (dim=384)" in captured.err


def test_legacy_dry_run_invocation(capsys, tmp_path):
    config_file = _write_minimal_config(tmp_path)

    with logger_to_stderr():
        exit_code = main(["--config", str(config_file), "--dry-run"])

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "=== General Configuration ===" in captured.err
    assert "No command provided" not in captured.err
