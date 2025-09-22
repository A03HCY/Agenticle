from typing import List, Dict, Union, Iterator, Optional

from .agent import Agent
from .tool  import Tool
from .event import Event

class Group:
    """
    A team of Agents that can collaborate to accomplish complex tasks.

    A Group contains a set of Agents. It automatically "wires" them up so that
    each Agent can see the other Agents in the team as expert tools to be called upon.
    """

    def __init__(
        self,
        name: str,
        agents: List[Agent],
        manager_agent_name: Optional[str] = None,
        shared_tools: Optional[List[Tool]] = None,
        mode: str = 'broadcast'
    ):
        """Initializes an Agent Group.

        Args:
            name (str): The name of the group.
            agents (List[Agent]): A list of Agent instances in the group.
            manager_agent_name (str, optional): The name of the designated manager Agent.
                                                If not provided, the first Agent in the list is used.
            shared_tools (Optional[List[Tool]], optional): A list of tools shared by the group.
            mode (str, optional): The communication mode between Agents.
                                  'broadcast': All Agents can call each other.
                                  'manager_delegation': Only the manager can call other Agents.
        """
        self.name = name
        self.agents: Dict[str, Agent] = {agent.name: agent for agent in agents}
        self.shared_tools = shared_tools or []
        self.mode = mode

        if not agents:
            raise ValueError("Group must contain at least one agent.")

        # Determine the Manager Agent
        if manager_agent_name:
            if manager_agent_name not in self.agents:
                raise ValueError(f"Manager agent '{manager_agent_name}' not found in the group.")
            self.manager_agent = self.agents[manager_agent_name]
        else:
            self.manager_agent = list(self.agents.values())[0]  # Default to the first one
        
        # Core: Automatically wire the agents to know each other
        self._wire_agents()

    def _wire_agents(self):
        """
        Configures the toolset for each agent in the group based on the set mode.
        """
        all_agents_as_tools = {name: agent.as_tool() for name, agent in self.agents.items()}

        for agent_name, agent in self.agents.items():
            final_toolset = []
            
            # 1. Add the agent's own native tools
            if hasattr(agent, 'original_tools'):
                final_toolset.extend(agent.original_tools)
            
            # 2. Add group shared tools
            final_toolset.extend(self.shared_tools)

            # 3. Add other agents as tools based on the mode
            is_manager = (agent_name == self.manager_agent.name)

            if self.mode == 'broadcast' or (self.mode == 'manager_delegation' and is_manager):
                # In broadcast mode, all agents, or in delegation mode, the manager, can call other agents
                for other_name, other_agent_as_tool in all_agents_as_tools.items():
                    if agent_name != other_name:
                        final_toolset.append(other_agent_as_tool)
            
            # 4. Update the agent's configuration
            agent._configure_with_tools(final_toolset)

    def run(self, stream: bool = False, **kwargs) -> Union[str, Iterator[Event]]:
        """
        Runs the entire Group to perform a task.
        The task will first be passed to the manager Agent.

        Args:
            stream (bool): If True, returns an event generator for real-time output.
                           If False, blocks until the task is complete and returns the final string.
            **kwargs: Input parameters required to start the manager Agent.

        Returns:
            Union[str, Iterator[Event]]: The final result or the event stream.
        """
        if stream:
            return self._run_stream(**kwargs)
        else:
            # For non-streaming, directly call the manager's non-streaming run method
            return self.manager_agent.run(stream=False, **kwargs)

    def _run_stream(self, **kwargs) -> Iterator[Event]:
        """Runs the main loop of the Group as an event generator."""
        
        # 1. Signal the start of the Group
        yield Event(f"Group:{self.name}", "start", {"manager": self.manager_agent.name, "input": kwargs})

        # 2. Get and start the manager Agent's event stream
        manager_stream = self.manager_agent.run(stream=True, **kwargs)
        
        final_result = f"Group '{self.name}' finished without a clear final answer."

        # 3. Iterate through the manager's stream and pass all events (including those from sub-agents it calls) out in real-time
        for event in manager_stream:
            # 4. Capture the manager Agent's own end signal to get the final result
            if event.source == f"Agent:{self.manager_agent.name}" and event.type == "end":
                final_result = event.payload.get("final_answer", final_result)
            
            # 5. Forward all events (regardless of source) directly
            yield event
        
        # 6. After all processes are finished, signal the end of the Group
        yield Event(f"Group:{self.name}", "end", {"result": final_result})
