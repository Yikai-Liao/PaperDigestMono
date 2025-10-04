"""Pytest helpers for path configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def pytest_addoption(parser: pytest.OptionGroup) -> None:
    """
    添加 pytest CLI 选项 --test-sample-size，用于控制测试样本量。
    
    环境变量 TEST_SAMPLE_SIZE 可覆盖此选项。
    默认值为 10，上限 1000（保护机制），0 表示使用完整数据集（不裁剪）。
    
    使用示例：
    - 本地运行：TEST_SAMPLE_SIZE=5 uv run --no-progress pytest -q
    - 或：uv run --no-progress pytest -q --test-sample-size=5
    - CI 中设置：export TEST_SAMPLE_SIZE=10 （或更小值以加速）
    """
    parser.addoption(
        "--test-sample-size",
        action="store",
        default=None,
        type=int,
        help="Limit sample size for tests. Env var TEST_SAMPLE_SIZE overrides. 0 means full dataset."
    )


@pytest.fixture(scope="session")
def test_sample_size(request: pytest.FixtureRequest) -> int:
    """
    会话级 fixture，提供测试样本量配置。
    
    优先读取环境变量 TEST_SAMPLE_SIZE，其次 CLI --test-sample-size。
    默认 10；<0 置为 0；>1000 限制为 1000。
    """
    env_val = os.getenv("TEST_SAMPLE_SIZE")
    if env_val is not None and env_val.isdigit():
        value = int(env_val)
    else:
        cli_val = request.config.getoption("test_sample_size")
        value = cli_val if cli_val is not None else 10
    
    if value < 0:
        value = 0
    elif value > 1000:
        value = 1000  # 保护上限，文档默认上限 10 但允许特殊放宽
    
    return value
