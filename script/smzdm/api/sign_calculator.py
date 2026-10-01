import hashlib
import re
from typing import Dict, Any, Union
from urllib.parse import urlparse, parse_qs

# 公共变量：用于 sign 计算的固定 key
# 该 key 与 smzdm App 客户端内置的一致，改动会导致所有接口返回 check Sign Fail
SECRET_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"


def calculate_sign(data: Dict[str, Any]) -> str:
    """
    计算 sign 签名（适用于 POST 请求的 data 参数）

    Args:
        data: 包含请求参数的字典

    Returns:
        计算出的 MD5 签名（大写）
    """
    return _generate_sign_from_dict(data)


def calculate_sign_from_url(url: str) -> str:
    """
    从 GET 请求的 URL 中提取参数并计算 sign 签名

    Args:
        url: 包含查询参数的完整 URL

    Returns:
        计算出的 MD5 签名（大写）
    """
    # 解析 URL 获取查询参数
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    # 将查询参数转换为字典格式（取第一个值，因为 parse_qs 返回列表）
    params_dict = {}
    for key, values in query_params.items():
        if values:  # 确保值不为空
            params_dict[key] = values[0]

    return _generate_sign_from_dict(params_dict)


def calculate_sign_from_params(params: Union[Dict[str, Any], str]) -> str:
    """
    通用的 sign 计算函数，支持字典参数或 URL 字符串

    Args:
        params: 可以是字典格式的参数，或者包含查询参数的 URL 字符串

    Returns:
        计算出的 MD5 签名（大写）
    """
    if isinstance(params, str):
        # 如果是字符串，判断是否为完整 URL 还是查询字符串
        if params.startswith('http'):
            return calculate_sign_from_url(params)
        else:
            # 处理纯查询字符串，如 "a=1&b=2"
            query_params = parse_qs(params)
            params_dict = {}
            for key, values in query_params.items():
                if values:
                    params_dict[key] = values[0]
            return _generate_sign_from_dict(params_dict)
    elif isinstance(params, dict):
        return calculate_sign(params)
    else:
        raise ValueError("params 必须是字典或字符串类型")


def _generate_sign_from_dict(data: Dict[str, Any]) -> str:
    """
    从字典参数生成 sign 签名的内部函数

    Args:
        data: 包含请求参数的字典

    Returns:
        计算出的 MD5 签名（大写）
    """
    # 1. 获取所有 key 并按字母顺序排序
    sorted_keys = sorted(data.keys())

    # 2. 构建 key=value 对，并用 & 连接（跳过空值）
    params = []
    for key in sorted_keys:
        value = data[key]
        # 跳过空值（None、空字符串、空列表等）
        if value is not None and value != "" and value != []:
            # 转换为字符串并去除空格和换行符
            value_str = re.sub(r'[^\S\r\n]+', '', str(value))
            # value_str = str(value).strip().replace('\n', '').replace('\r', '').replace(' ', '')
            # 再次检查处理后的值是否为空
            if value_str:
                params.append(f"{key}={value_str}")

    # 3. 用 & 连接所有参数
    query_string = "&".join(params)
    # print(params)

    # 4. 在最后拼接固定的 key
    query_string += f"&key={SECRET_KEY}"
    # print(query_string)
    # 5. 计算 MD5
    md5_hash = hashlib.md5(query_string.encode('utf-8')).hexdigest()

    # 6. 返回大写的 MD5
    return md5_hash.upper()

