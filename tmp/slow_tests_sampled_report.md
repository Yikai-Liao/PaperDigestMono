# Top-20 慢测试报告 (采样大小: 10)

| Rank | Seconds | Node ID | File Path |
|------|---------|---------|-----------|
| 1 | 0.09 | tests/web/test_app.py::test_run_nonexistent_job | tests/web/test_app.py |
| 2 | 0.02 | tests/web/test_app.py::test_metrics_endpoint | tests/web/test_app.py |
| 3 | 0.02 | tests/summary/test_cli_summarize.py::test_cli_summarize_generates_outputs | tests/summary/test_cli_summarize.py |
| 4 | 0.01 | tests/cli/test_cli_serve.py::test_cli_serve_dry_run | tests/cli/test_cli_serve.py |
| 5 | 0.01 | tests/web/test_app.py::test_run_job_successfully | tests/web/test_app.py |
| 6 | 0.01 | tests/web/test_app.py::test_run_nonexistent_job | tests/web/test_app.py |
| 7 | 0.01 | tests/scheduler/test_service.py::test_scheduler_service_dry_run | tests/scheduler/test_service.py |
| 8 | 0.01 | tests/web/test_app.py::test_list_jobs | tests/web/test_app.py |
| 9 | 0.01 | tests/web/test_app.py::test_health_check | tests/web/test_app.py |
| 10 | 0.01 | tests/scheduler/test_service.py::test_export_metrics_prometheus | tests/scheduler/test_service.py |
| 11 | 0.01 | tests/cli/test_cli_config.py::test_config_explain_text_output | tests/cli/test_cli_config.py |
| 12 | 0.01 | tests/scheduler/test_service.py::test_metrics_record_failure | tests/scheduler/test_service.py |
| 13 | 0.01 | tests/summary/test_cli.py::test_cli_summarize_dry_run | tests/summary/test_cli.py |
| 14 | 0.01 | tests/cli/test_cli_status.py::test_legacy_dry_run_invocation | tests/cli/test_cli_status.py |
| 15 | 0.01 | tests/cli/test_cli_status.py::test_status_dry_run_reports_sections | tests/cli/test_cli_status.py |
| 16 | 0.01 | tests/scheduler/test_service.py::test_metrics_record_success | tests/scheduler/test_service.py |
| 17 | 0.01 | tests/scheduler/test_service.py::test_scheduler_service_start_and_shutdown | tests/scheduler/test_service.py |
| 18 | 0.01 | tests/summary/test_cli_summarize.py::test_cli_summarize_dry_run | tests/summary/test_cli_summarize.py |
| 19 | 0.01 | tests/migration/test_legacy.py::test_migrator_merges_preferences_and_summaries | tests/migration/test_legacy.py |
| 20 | 0.01 | tests/cli/test_cli_config.py::test_config_check_validation_error | tests/cli/test_cli_config.py |

**说明**: 该报告基于 pytest --durations=20 输出解析，仅包含采样测试 (TEST_SAMPLE_SIZE=10)。总运行时间约 3.19s，1 个测试失败 (tests/web/test_app.py::test_metrics_endpoint)，详见 tmp/pytest_sampled_durations.txt。