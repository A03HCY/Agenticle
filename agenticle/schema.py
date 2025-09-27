from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Endpoint:
    """
    Stores API endpoint and credential information.
    
    Attributes:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the API.
        name (str): The name of the endpoint configuration.
    """
    api_key: str
    base_url: str
    name: str = field(default="default")

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
