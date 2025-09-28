from typing  import List, Dict, Any, Optional, Union
from .agent  import Agent
from .group  import Group
from .tool   import Tool
from .schema import Endpoint

import yaml

class Model:
    def __init__(self, path: str, tools: Optional[List[Tool]] = None, endpoints: Optional[List[Endpoint]] = None):
        with open(path, 'r', encoding='utf-8') as f:
            self.config: Dict[str, Any] = yaml.safe_load(f)
        
        self.tools: Dict[str, Tool] = {tool.name: tool for tool in tools} if tools else {}
        self.endpoints: Dict[str, Endpoint] = self._load_endpoints(endpoints)
        
        self.agents: Dict[str, Agent] = {}
        self.groups: Dict[str, Group] = {}
        self._create_all()

    def _load_endpoints(self, external_endpoints: Optional[List[Endpoint]] = None) -> Dict[str, Endpoint]:
        endpoints: Dict[str, Endpoint] = {}
        if "endpoints" in self.config:
            for name, config in self.config["endpoints"].items():
                endpoints[name] = Endpoint(**config)
        if external_endpoints:
            for endpoint in external_endpoints:
                endpoints[endpoint.name] = endpoint
        return endpoints

    def _create_all(self):
        agent_configs = self.config.get("agents", [])
        group_configs = self.config.get("groups", [])
        
        entities: Dict[str, Union[Agent, Group]] = {}
        unresolved_agents = list(agent_configs)
        unresolved_groups = list(group_configs)

        last_unresolved_count = -1
        while unresolved_agents or unresolved_groups:
            current_unresolved_count = len(unresolved_agents) + len(unresolved_groups)
            if current_unresolved_count == last_unresolved_count:
                raise RuntimeError("Circular or unresolved dependency detected in configuration.")
            last_unresolved_count = current_unresolved_count

            # Attempt to resolve agents
            remaining_agents = []
            for config in unresolved_agents:
                try:
                    agent = self._try_create_agent(config, entities)
                    entities[agent.name] = agent
                    self.agents[agent.name] = agent
                except ValueError:
                    remaining_agents.append(config)
            unresolved_agents = remaining_agents

            # Attempt to resolve groups
            remaining_groups = []
            for config in unresolved_groups:
                try:
                    group = self._try_create_group(config, entities)
                    entities[group.name] = group
                    self.groups[group.name] = group
                except ValueError:
                    remaining_groups.append(config)
            unresolved_groups = remaining_groups

    def _try_create_agent(self, config: Dict, entities: Dict) -> Agent:
        tools = []
        if "tools" in config:
            for name in config["tools"]:
                if name in self.tools:
                    tools.append(self.tools[name])
                elif name in entities:
                    tools.append(entities[name].as_tool())
                else:
                    raise ValueError(f"Dependency '{name}' not ready.")
        
        endpoint_name = config.get("endpoint", "default")
        endpoint = self.endpoints.get(endpoint_name)
        if not endpoint:
            raise ValueError(f"Endpoint '{endpoint_name}' not found.")

        return Agent(
            name=config["name"],
            description=config.get("description", ""),
            input_parameters=config.get("input_parameters", []),
            tools=tools,
            endpoint=endpoint,
            model_id=config["model_id"],
        )

    def _try_create_group(self, config: Dict, entities: Dict) -> Group:
        members = []
        if "agents" in config:
            for name in config["agents"]:
                if name in entities:
                    members.append(entities[name])
                else:
                    raise ValueError(f"Dependency '{name}' not ready.")
        
        shared_tools = []
        if "shared_tools" in config:
            for name in config["shared_tools"]:
                if name in self.tools:
                    shared_tools.append(self.tools[name])
                elif name in entities:
                    shared_tools.append(entities[name].as_tool())
                else:
                    raise ValueError(f"Dependency '{name}' not ready.")

        return Group(
            name=config["name"],
            agents=members,
            description=config.get("description"),
            manager_agent_name=config.get("manager_agent_name"),
            shared_tools=shared_tools,
            mode=config.get("mode", "broadcast"),
        )

def modelize(
    agents: List[Agent] = [],
    groups: List[Group] = [],
    path: str = 'agent_config.yaml',
    save_endpoints: bool = False
):
    """
    Serializes lists of Agent and Group objects, including nested structures,
    into a YAML configuration file.
    """
    discovered_agents = {}
    discovered_groups = {}

    def _discover(entity: Union[Agent, Group]):
        if isinstance(entity, Agent):
            if entity.name not in discovered_agents:
                discovered_agents[entity.name] = entity
                # Discover agents/groups used as tools
                for tool in entity.original_tools:
                    if hasattr(tool, 'source_entity'):
                        _discover(tool.source_entity)
        elif isinstance(entity, Group):
            if entity.name not in discovered_groups:
                discovered_groups[entity.name] = entity
                # Discover group members
                for member in entity.agent_sequence:
                    _discover(member)
                # Discover shared tools that are agents/groups
                for tool in entity.shared_tools:
                    if hasattr(tool, 'source_entity'):
                        _discover(tool.source_entity)
    
    for agent in agents:
        _discover(agent)
    for group in groups:
        _discover(group)

    endpoints = {}
    for agent in discovered_agents.values():
        if agent.endpoint and agent.endpoint.name not in endpoints:
            endpoints[agent.endpoint.name] = agent.endpoint.to_dict()

    config = {
        "endpoints": endpoints,
        "agents": [agent.to_dict() for agent in discovered_agents.values()],
        "groups": [group.to_dict() for group in discovered_groups.values()],
    }

    if not save_endpoints:
        config.pop("endpoints")

    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
