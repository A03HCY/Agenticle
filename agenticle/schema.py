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