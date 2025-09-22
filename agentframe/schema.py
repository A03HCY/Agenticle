from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    """
    用于存储 API 的接入点和凭证信息。
    
    Attributes:
        api_key (str): 用于认证的 API 密钥。
        base_url (str): API 的基础 URL。
    """
    api_key: str
    base_url: str