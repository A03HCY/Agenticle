from dataclasses import dataclass, field, asdict
from typing      import Optional
from .utils      import api_key, base_url

@dataclass(frozen=True)
class Endpoint:
    """
    Stores API endpoint and credential information.
    
    Attributes:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the API.
        name (str): The name of the endpoint configuration.
    """
    api_key: str = field(default=api_key)
    base_url: str = field(default=base_url)
    name: str = field(default="env")
    platform: Optional[str] = field(default='openai_compat')

    def to_dict(self):
        return asdict(self)

@dataclass(frozen=True)
class Vote:
    """
    Stores a vote for a group.
    
    Attributes:
        agent_name (str): The name of the agent that made the vote.
        vote (str): The vote.
        reason (str): The reason for the vote.
    """
    agent_name: str
    vote: str
    reason: str

@dataclass(frozen=True)
class Response:
    success: bool = True
    thinking: str = ""
    content: str = ""
    tool_calls: list = field(default_factory=list)
    error: Optional[str] = None
