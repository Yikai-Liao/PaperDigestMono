from typing import Any

def sample_items(items: Any, n: int) -> Any:
    """
    通用的采样函数，用于测试中限制样本量。
    
    如果 n == 0，返回完整 items（不裁剪）。
    支持 list/tuple/dict、pandas.DataFrame、polars.DataFrame、
    duckdb.QueryResult 等通过 head 或切片方式采样。
    
    Args:
        items: 输入数据，支持多种类型。
        n: 采样数量，0 表示完整数据。
    
    Returns:
        采样后的数据，类型与输入一致或兼容。
    """
    if n == 0 or items is None:
        return items
    
    if isinstance(items, (list, tuple)):
        return items[:n]
    
    if isinstance(items, dict):
        return dict(list(items.items())[:n])
    
    if hasattr(items, "head") and callable(items.head):
        # 支持 polars/pandas DataFrame
        return items.head(n)
    
    if hasattr(items, "__len__") and hasattr(items, "__getitem__"):
        # 通用可切片对象，如 duckdb.QueryResult
        try:
            return items[:n]
        except (TypeError, IndexError):
            pass
    
    # 无法采样，返回原数据
    return items


def safe_sample(items: Any, n: int) -> Any:
    """
    安全的采样包装器，在采样失败时打印错误并返回原数据。
    
    用于测试中避免采样异常中断整个测试套件。
    
    Args:
        items: 输入数据。
        n: 采样数量。
    
    Returns:
        采样结果或原数据。
    """
    try:
        return sample_items(items, n)
    except Exception as e:
        print(f"Sampling failed for items of type {type(items)}: {e}")
        return items