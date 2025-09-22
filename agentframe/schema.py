from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    """
    Stores API endpoint and credential information.
    
    Attributes:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the API.
    """
    api_key: str
    base_url: str
