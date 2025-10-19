from typing      import List, Dict, Union, Iterator, Optional, Any
from collections import Counter
from functools   import partial

from .agent  import Agent
from .tool   import Tool, Workspace
from .event  import Event, EventBroker
from .schema import Vote
from .optimizer import BaseOptimizer, CompetitionOptimizer

import concurrent.futures
import json

class Group:
    """
    A team of Agents that can collaborate to accomplish complex tasks.

    A Group contains a set of Agents. It automatically "wires" them up so that
    each Agent can see the other Agents in the team as expert tools to be called upon.
    """

    def __init__(
        self,
        name: str,
        agents: List[Union[Agent, 'Group']],
        description: Optional[str] = None,
        manager_agent_name: Optional[str] = None,
        shared_tools: Optional[List[Tool]] = None,
        workspace: Optional[Union[str, Workspace]] = None,
        mode: str = 'broadcast',
        optimizer: Optional[BaseOptimizer] = None
    ):
        """Initializes an Agent Group.

        Args:
            name (str): The name of the group.
            agents (List[Agent]): A list of Agent instances in the group.
            description (Optional[str], optional): A description of the group's purpose.
            manager_agent_name (str, optional): The name of the designated manager Agent.
                                                If not provided, the first Agent in the list is used.
            shared_tools (Optional[List[Tool]], optional): A list of tools shared by the group.
            workspace (Optional[Union[str, Workspace]], optional): A shared workspace for the group.
            mode (str, optional): The communication mode between Agents.
                                  'broadcast': All Agents can call each other.
                                  'manager_delegation': Only the manager can call other Agents.
                                  'round_robin': Agents execute sequentially in a chain.
                                  'voting': All Agents receive the same input and vote on a final answer from a given set of options.
        """
        self.name = name
        self.description = description or f"A group of agents named {name}."
        self.agents: Dict[str, Union[Agent, 'Group']] = {agent.name: agent for agent in agents}
        self.agent_sequence: List[Union[Agent, 'Group']] = agents
        self.shared_tools = shared_tools or []
        self.mode = mode
        self.optimizer = optimizer
        
        if mode not in ['broadcast', 'manager_delegation', 'round_robin', 'voting', 'competition']:
            raise ValueError(f"Unsupported mode: {mode}")

        if mode == 'competition' and not self.optimizer:
            self.optimizer = CompetitionOptimizer()

        self.workspace = None
        self.manager_agent = None
        self._should_resume = False

        if not agents:
            raise ValueError("Group must contain at least one agent.")

        if isinstance(workspace, Workspace):
            self.workspace = workspace
        elif isinstance(workspace, str):
            self.workspace = Workspace(path=workspace)
        
        if self.workspace:
            self.shared_tools.extend(self.workspace.get_tools())

        if mode == 'round_robin' and manager_agent_name:
            print("Warning: 'manager_agent_name' is ignored in 'round_robin' mode.")

        if manager_agent_name:
            if manager_agent_name not in self.agents:
                raise ValueError(f"Manager agent '{manager_agent_name}' not found in the group.")
            self.manager_agent = self.agents[manager_agent_name]
        elif self.agent_sequence:
            self.manager_agent = self.agent_sequence[0]
        
        self._wire_agents()

    def _wire_agents(self):
        """
        Configures the toolset and context for each agent in the group based on the set mode.
        """
        all_agents_as_tools = {name: agent.as_tool() for name, agent in self.agents.items()}

        for i, agent in enumerate(self.agent_sequence):
            final_toolset = []
            
            if hasattr(agent, 'original_tools'):
                final_toolset.extend(agent.original_tools)
            
            # Special handling for workspace tools to inject the agent context
            for tool in self.shared_tools:
                if tool.name == 'read_file' and isinstance(agent, Agent):
                    # Create a new function with the 'agent' argument pre-filled
                    bound_func = partial(tool.func, agent=agent)
                    
                    # Create a new Tool instance for this agent, excluding the 'agent' parameter from the LLM's view
                    analysis = tool.func.__globals__['analyze_tool_function'](tool.func)
                    new_params = [p for p in analysis['parameters'] if p['name'] != 'agent']
                    
                    agent_specific_tool = Tool(
                        func=bound_func,
                        name=tool.name,
                        description=tool.description,
                        parameters=new_params
                    )
                    final_toolset.append(agent_specific_tool)
                else:
                    final_toolset.append(tool)

            extra_context = {"collaboration_mode": self.mode}
            is_manager = (agent.name == self.manager_agent.name)

            if self.mode == 'round_robin':
                extra_context["mode_description"] = "You are part of a sequential pipeline. Receive input, perform your specific task, and then use 'end_task' with a clear 'final_answer' for the next agent."
                prev_agent = self.agent_sequence[i-1].name if i > 0 else "the initial user input"
                next_agent = self.agent_sequence[i+1].name if i < len(self.agent_sequence) - 1 else "the final output"
                extra_context["position_in_chain"] = f"You will receive input from '{prev_agent}' and your output will be passed to '{next_agent}'."
            
            elif self.mode == 'manager_delegation':
                if is_manager:
                    extra_context["mode_description"] = "You are the manager. Your role is to break down the main task and delegate sub-tasks to the expert agents in your team. You are the only one who can call other agents."
                else:
                    extra_context["mode_description"] = "You are an expert agent. You must wait for instructions from your manager and execute the tasks they assign to you."
                
                if is_manager:
                    for other_name, other_agent_as_tool in all_agents_as_tools.items():
                        if agent.name != other_name:
                            final_toolset.append(other_agent_as_tool)

            elif self.mode == 'broadcast':
                for other_name, other_agent_as_tool in all_agents_as_tools.items():
                    if agent.name != other_name:
                        final_toolset.append(other_agent_as_tool)
            
            elif self.mode == 'voting':
                extra_context["mode_description"] = "You are part of a voting panel. You will receive the same task as your peers. Perform the task to the best of your ability and provide a definitive final answer. Your answer will be compared with others to reach a consensus."

            elif self.mode == 'competition':
                extra_context["mode_description"] = "You are in a competition. You will receive the same task as your peers. Perform the task to the best of your ability and provide a clear, comprehensive final answer. The best answer among all participants will be chosen."

            if isinstance(agent, Agent):
                agent._configure_with_tools(final_toolset, extra_context=extra_context)
            elif isinstance(agent, Group):
                # Recursively wire sub-groups
                agent._wire_agents()

    def as_tool(self) -> Tool:
        """Wraps the entire Group instance into a Tool, allowing it to be called by other agents."""
        if not self.manager_agent:
            raise ValueError("A manager agent must be defined to expose the group as a tool.")

        # Dynamically create a wrapper function that calls the group's run method
        def group_runner(stream: bool = True, **kwargs):
            return self.run(stream=stream, **kwargs)

        group_runner.__name__ = self.name
        group_runner.__doc__ = self.description
        
        # Dynamically build the function signature based on the manager agent's input parameters
        from inspect import Parameter, Signature
        manager_input_params = self.manager_agent.input_parameters
        params = [
            Parameter(name=p['name'], kind=Parameter.POSITIONAL_OR_KEYWORD) 
            for p in manager_input_params
        ]
        group_runner.__signature__ = Signature(params)

        # Mark as an agent tool so it's displayed correctly in the prompt
        tool = Tool(func=group_runner, is_agent_tool=True, is_group_tool=True)
        setattr(tool, 'source_entity', self)
        return tool

    def run(self, stream: bool = True, retries: int = 0, **kwargs) -> Union[str, Iterator[Event]]:
        """
        Runs the entire Group to perform a task.
        The execution flow depends on the group's mode.

        Args:
            stream (bool): If True, returns an event generator for real-time output.
                           If False, blocks until the task is complete and returns the final string.
            retries (int): The number of times to retry if an agent fails in a recoverable way 
                           (e.g., invalid output format in 'voting' mode). Defaults to 0.
            **kwargs: Input parameters required to start the group task.
                      If `mode` is 'voting', `kwargs` must include an 'options'
                      key with a dictionary of choices for the agents to vote on.

        Returns:
            Union[str, Iterator[Event]]: The final result or the event stream.
        """
        resume_run = self._should_resume
        if resume_run:
            self._should_resume = False # Reset after use

        runner_kwargs = {"resume": resume_run, **kwargs}

        if self.mode == 'round_robin':
            runner = self._run_stream_round_robin
        elif self.mode == 'voting':
            runner = self._run_stream_voting
            runner_kwargs["retries"] = retries # Add retries for voting mode
        elif self.mode == 'competition':
            runner = self._run_stream_competition
        else:
            runner = self._run_stream_manager_based

        if stream:
            return runner(**runner_kwargs)
        else:
            final_answer = ""
            for event in runner(**runner_kwargs):
                if event.type == "end" and event.source == f"Group:{self.name}":
                    final_answer = event.payload.get("result", "")
            return final_answer

    def _run_stream_round_robin(self, resume: bool = False, **kwargs) -> Iterator[Event]:
        """Runs the group in a sequential, round-robin fashion."""
        if resume:
            yield Event(f"Group:{self.name}", "resume", {"mode": "round_robin"})
        else:
            yield Event(f"Group:{self.name}", "start", {"mode": "round_robin", "input": kwargs})

        current_input = kwargs
        final_result = f"Group '{self.name}' finished round-robin without a clear final answer."

        for i, agent in enumerate(self.agent_sequence):
            yield Event(f"Group:{self.name}", "step", {"agent_name": agent.name, "step": i + 1})
            
            # The first agent in a new run gets the kwargs, subsequent agents get the output of the previous one.
            # In a resumed run, we assume the flow continues and don't re-inject kwargs.
            agent_input = current_input if i == 0 and not resume else {"input": final_result}
            
            agent_stream = agent.run(stream=True, resume=resume, **agent_input)
            
            agent_final_answer = None
            for event in agent_stream:
                yield event
                if event.source == f"Agent:{agent.name}" and event.type == "end":
                    agent_final_answer = event.payload.get("final_answer")
            
            if agent_final_answer is None:
                error_msg = f"Agent '{agent.name}' did not provide a final_answer in round-robin step {i+1}."
                yield Event(f"Group:{self.name}", "error", {"message": error_msg})
                final_result = error_msg
                break

            current_input = {"input": agent_final_answer}
            final_result = agent_final_answer

        yield Event(f"Group:{self.name}", "end", {"result": final_result})

    def _run_stream_competition(self, resume: bool = False, **kwargs) -> Iterator[Event]:
        """Runs the group in a parallel, competition-based fashion."""
        if resume:
            yield Event(f"Group:{self.name}", "resume", {"mode": "competition"})
        else:
            yield Event(f"Group:{self.name}", "start", {"mode": "competition", "input": kwargs})

        event_broker = EventBroker()
        agent_results: List[Dict[str, Any]] = []

        def agent_worker(agent: Agent, agent_kwargs: Dict, broker: EventBroker):
            """Runs an agent and captures its final_answer."""
            final_answer = None
            try:
                agent_stream = agent.run(stream=True, resume=resume, **agent_kwargs)
                for event in agent_stream:
                    broker.queue.put(event)
                    if event.type == "end":
                        final_answer = event.payload.get("final_answer")
            except Exception as e:
                error_msg = f"Agent {agent.name} threw an exception: {e}"
                broker.emit(f"Group:{self.name}", "error", {"agent_name": agent.name, "message": error_msg})
            
            broker.emit(f"Group:{self.name}", "agent_completed", {"agent_name": agent.name, "result": final_answer})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for agent in self.agent_sequence:
                executor.submit(agent_worker, agent, kwargs, event_broker)
            
            completed_agents = 0
            while completed_agents < len(self.agent_sequence):
                event: Event = event_broker.queue.get()
                if event.type == "agent_completed":
                    completed_agents += 1
                    if event.payload.get("result"):
                        agent_results.append(event.payload)
                else:
                    yield event
        
        if not agent_results:
            final_result = "No consensus reached: no agents provided a valid result."
            yield Event(f"Group:{self.name}", "error", {"message": final_result})
            yield Event(f"Group:{self.name}", "end", {"result": final_result})
            return

        yield Event(f"Group:{self.name}", "step", {"action": "Optimizing results..."})
        
        # Extract the task description from kwargs. A bit simplistic, assumes a 'task' or 'input' key.
        task_description = kwargs.get('task', kwargs.get('input', ''))
        
        # Run the optimizer
        try:
            final_answers = [res['result'] for res in agent_results]
            best_result = self.optimizer.optimize(task_description=str(task_description), results=final_answers)
        except Exception as e:
            error_msg = f"Optimizer failed: {e}"
            yield Event(f"Group:{self.name}", "error", {"message": error_msg})
            yield Event(f"Group:{self.name}", "end", {"result": error_msg})
            return

        yield Event(f"Group:{self.name}", "end", {
            "result": best_result,
            "details": {
                "all_results": agent_results
            }
        })

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the group's configuration to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "agents": [agent.name for agent in self.agent_sequence],
            "manager_agent_name": self.manager_agent.name if self.manager_agent else None,
            "shared_tools": [tool.name for tool in self.shared_tools],
            "workspace": self.workspace.path if self.workspace else None,
            "mode": self.mode
        }

    def _run_stream_voting(self, resume: bool = False, retries: int = 0, **kwargs) -> Iterator[Event]:
        """Runs the group in a parallel, voting-based fashion, streaming all sub-events."""
        if resume:
            yield Event(f"Group:{self.name}", "resume", {"mode": "voting"})
        else:
            yield Event(f"Group:{self.name}", "start", {"mode": "voting", "input": kwargs})

        voting_options = kwargs.get("options", {})
        if not voting_options:
            yield Event(f"Group:{self.name}", "error", {"message": "Voting mode requires 'options' dictionary."})
            yield Event(f"Group:{self.name}", "end", {"result": "Error: Missing voting options."})
            return

        event_broker = EventBroker()
        agent_votes: List[Vote] = []

        def agent_worker(agent: Agent, agent_kwargs: Dict, broker: EventBroker):
            """Runs an agent, processes its vote, and handles retries for invalid formats."""
            vote_data = None
            final_answer = None

            for attempt in range(retries + 1):
                try:
                    agent_kwargs_with_options = {**agent_kwargs, "options": voting_options}
                    
                    if attempt > 0:
                        agent.reset()
                        agent.history.append({
                            "role": "user",
                            "content": "Your previous response was not in the correct format. Please try again. Your final answer MUST be a valid JSON object with 'vote' and 'reason' keys."
                        })
                        broker.emit(f"Group:{self.name}", "retry", {"agent_name": agent.name, "action": "retry", "attempt": attempt})

                    current_resume = resume if attempt == 0 else False
                    agent_stream = agent.run(stream=True, resume=current_resume, **agent_kwargs_with_options)
                    
                    for event in agent_stream:
                        broker.queue.put(event)
                        if event.type == "end":
                            final_answer = event.payload.get("final_answer")
                
                except Exception as e:
                    error_msg = f"Agent {agent.name} threw an exception on attempt {attempt + 1}: {e}"
                    broker.emit(f"Group:{self.name}", "error", {"agent_name": agent.name, "message": error_msg})
                    continue

                if final_answer:
                    try:
                        result_json = json.loads(final_answer)
                        if "vote" in result_json and "reason" in result_json:
                            vote_data = {
                                "agent_name": agent.name,
                                "vote": result_json["vote"],
                                "reason": result_json["reason"]
                            }
                            break
                    except (json.JSONDecodeError, TypeError):
                        error_msg = f"Agent {agent.name} returned an invalid JSON format on attempt {attempt + 1}."
                        broker.emit(f"Group:{self.name}", "error", {"agent_name": agent.name, "message": error_msg})

            if not vote_data and final_answer is not None:
                error_msg = f"Agent {agent.name} failed to provide a valid vote after {retries + 1} attempts."
                broker.emit(f"Group:{self.name}", "error", {"agent_name": agent.name, "message": error_msg})

            broker.emit(f"Group:{self.name}", "agent_completed", {"agent_name": agent.name, "vote_data": vote_data})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for agent in self.agent_sequence:
                executor.submit(agent_worker, agent, kwargs, event_broker)
            
            completed_agents = 0
            while completed_agents < len(self.agent_sequence):
                event: Event = event_broker.queue.get()
                if event.type == "agent_completed":
                    completed_agents += 1
                    vote_data = event.payload.get("vote_data")
                    if vote_data:
                        vote_obj = Vote(**vote_data)
                        agent_votes.append(vote_obj)
                        yield Event(f"Group:{self.name}", "step", {"agent_name": vote_obj.agent_name, "vote": vote_obj.vote, "reason": vote_obj.reason})
                else:
                    yield event
        
        if not agent_votes:
            final_result = "No consensus reached: no agents provided a valid vote."
            yield Event(f"Group:{self.name}", "error", {"message": final_result})
            yield Event(f"Group:{self.name}", "end", {"result": final_result})
            return

        vote_counts = Counter(v.vote for v in agent_votes)
        most_common_vote = vote_counts.most_common(1)[0][0]
        
        full_results = [
            {"agent": v.agent_name, "vote": v.vote, "reason": v.reason}
            for v in agent_votes
        ]
        
        yield Event(f"Group:{self.name}", "end", {
            "result": most_common_vote,
            "details": {
                "vote_counts": dict(vote_counts),
                "all_votes": full_results
            }
        })

    def _run_stream_manager_based(self, resume: bool = False, **kwargs) -> Iterator[Event]:
        """Runs the main loop for manager-based modes (broadcast, manager_delegation)."""
        if resume:
            yield Event(f"Group:{self.name}", "resume", {"manager": self.manager_agent.name})
        else:
            yield Event(f"Group:{self.name}", "start", {"manager": self.manager_agent.name, "input": kwargs})

        manager_stream = self.manager_agent.run(stream=True, resume=resume, **kwargs)
        
        final_result = f"Group '{self.name}' finished without a clear final answer."

        for event in manager_stream:
            if event.source == f"Agent:{self.manager_agent.name}" and event.type == "end":
                final_result = event.payload.get("final_answer", final_result)
            
            yield event
        
        yield Event(f"Group:{self.name}", "end", {"result": final_result})
