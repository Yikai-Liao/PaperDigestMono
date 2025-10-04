# Slow Tests Report

## Overview
This report analyzes the top-20 slowest tests from the safe test suite (excluding flagged tests with potential network or data/ write risks). All durations are under 0.02s, indicating generally fast execution. No flagged reasons apply to these safe tests. Notes confirm no additional risks.

## Top-20 Slowest Tests

| Rank | Seconds | NodeID | File | Flagged Reasons | Notes |
|------|---------|--------|------|-----------------|-------|
| 1 | 0.02 | tests/summary/test_cli_summarize.py::test_cli_summarize_generates_outputs | tests/summary/test_cli_summarize.py | [] | Safe test, no network/write risks detected. |
| 2 | 0.01 | tests/web/test_app.py::test_metrics_endpoint | tests/web/test_app.py | [] | Safe test, no network/write risks detected. (Note: This test failed due to config issue, but duration captured.) |
| 3 | 0.01 | tests/cli/test_cli_serve.py::test_cli_serve_dry_run | tests/cli/test_cli_serve.py | [] | Safe test, no network/write risks detected. |
| 4 | 0.01 | tests/web/test_app.py::test_run_nonexistent_job | tests/web/test_app.py | [] | Safe test, no network/write risks detected. |
| 5 | 0.01 | tests/web/test_app.py::test_health_check | tests/web/test_app.py | [] | Safe test, no network/write risks detected. |
| 6 | 0.01 | tests/scheduler/test_service.py::test_export_metrics_prometheus | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 7 | 0.01 | tests/web/test_app.py::test_run_job_successfully | tests/web/test_app.py | [] | Safe test, no network/write risks detected. |
| 8 | 0.01 | tests/cli/test_cli_status.py::test_legacy_dry_run_invocation | tests/cli/test_cli_status.py | [] | Safe test, no network/write risks detected. |
| 9 | 0.01 | tests/web/test_app.py::test_list_jobs | tests/web/test_app.py | [] | Safe test, no network/write risks detected. |
| 10 | 0.01 | tests/scheduler/test_service.py::test_scheduler_service_dry_run | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 11 | 0.01 | tests/scheduler/test_service.py::test_metrics_record_failure | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 12 | 0.01 | tests/cli/test_cli_config.py::test_config_explain_text_output | tests/cli/test_cli_config.py | [] | Safe test, no network/write risks detected. |
| 13 | 0.01 | tests/summary/test_cli.py::test_cli_summarize_dry_run | tests/summary/test_cli.py | [] | Safe test, no network/write risks detected. |
| 14 | 0.01 | tests/cli/test_cli_status.py::test_status_dry_run_reports_sections | tests/cli/test_cli_status.py | [] | Safe test, no network/write risks detected. |
| 15 | 0.01 | tests/scheduler/test_service.py::test_metrics_record_success | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 16 | 0.01 | tests/scheduler/test_service.py::test_scheduler_service_start_and_shutdown | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 17 | 0.01 | tests/summary/test_cli_summarize.py::test_cli_summarize_dry_run | tests/summary/test_cli_summarize.py | [] | Safe test, no network/write risks detected. |
| 18 | 0.01 | tests/migration/test_legacy.py::test_migrator_merges_preferences_and_summaries | tests/migration/test_legacy.py | [] | Safe test, no network/write risks detected. |
| 19 | 0.01 | tests/scheduler/test_service.py::test_scheduler_service_trigger_job | tests/scheduler/test_service.py | [] | Safe test, no network/write risks detected. |
| 20 | 0.01 | tests/cli/test_cli_config.py::test_config_check_json_success | tests/cli/test_cli_config.py | [] | Safe test, no network/write risks detected. |

## Additional Notes
- Total safe tests run: 55 (1 failed, 54 passed).
- Failure in tests/web/test_app.py::test_metrics_endpoint due to missing recommend_pipeline config (not related to network/write).
- Flagged tests (11 files) were excluded to avoid risks; see tmp/flagged_test_files.txt for details.