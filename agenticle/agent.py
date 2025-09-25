import os
import json
import jinja2
from openai import OpenAI
from typing import List, Dict, Any, Optional, Union, Iterator

from .schema import Endpoint
from .tool   import Tool, EndTaskTool
from .event  import Event
from .utils.parser import IncrementalXmlParser

class Agent:
    def __init__(
        self,
        name: str,
        description: str,
        input_parameters: List[Dict[str, Any]],
        tools: List[Tool],
        endpoint: Endpoint,
        model_id: str,
        prompt_template_path: Optional[str] = None,
        target_lang:str = 'English',
        max_steps: int = 10,
        optimize_tool_call: bool = False
    ):
        """Initializes the Agent.

        Args:
            name (str): The name of the agent.
            description (str): A description of the agent's purpose.
            input_parameters (List[Dict[str, Any]]): A list of dictionaries describing the agent's input parameters.
            tools (List[Tool]): A list of tools available to the agent.
            endpoint (Endpoint): The API endpoint configuration for the language model.
            model_id (str): The ID of the language model to use.
            prompt_template_path (Optional[str]): The path to a Jinja2 template for the system prompt.
            target_lang (str): The target language for the agent's responses.
            max_steps (int): The maximum number of steps the agent can take.
        """
        self.name = name
        self.description = description
        self.input_parameters = input_parameters
        self.model_id = model_id
        self.target_lang = target_lang
        self.optimize_tool_call = optimize_tool_call

        os.environ['OPENAI_API_KEY'] = endpoint.api_key
        
        self.endpoint = endpoint
        self.max_steps = max_steps
        self._client = OpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)

        self.original_tools: List[Tool] = tools[:]
        self.tools: Dict[str, Tool] = {tool.name: tool for tool in tools}
        
        if "end_task" in self.tools:
            print("Warning: A user-provided tool named 'end_task' is being overridden by the built-in final answer tool.")
        # 2. In any case, build in our standard EndTaskTool
        self.tools["end_task"] = EndTaskTool()

        self._api_tools: List[Dict[str, Any]] = [t.info for t in self.tools.values()]
        
        self.system_prompt: str = self._generate_system_prompt_from_template(prompt_template_path)
        
        self.history: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
    
    def _configure_with_tools(self, tools: List[Tool], extra_context: Optional[Dict[str, Any]] = None):
        """Reconfigures the agent with a given list of tools and extra context.

        Args:
            tools (List[Tool]): The new list of tools to configure the agent with.
            extra_context (Optional[Dict[str, Any]]): Extra data to pass to the prompt template.
        """
        self.tools = {tool.name: tool for tool in tools}
        self.tools["end_task"] = EndTaskTool() # Make sure end_task is always present
        
        # Regenerate API tools and system prompt
        self._api_tools = [t.info for t in self.tools.values()]
        self.system_prompt = self._generate_system_prompt_from_template(
            getattr(self, '_prompt_template_path', None),
            extra_context=extra_context
        )
        self.reset() # Reset history to apply new system prompt


    def _generate_system_prompt_from_template(self, template_path: Optional[str] = None, extra_context: Optional[Dict[str, Any]] = None) -> str:
        """Loads and renders the system prompt from a Jinja2 template file.

        Args:
            template_path (Optional[str]): The path to the Jinja2 template file. 
                                           If None, a default path is used.
            extra_context (Optional[Dict[str, Any]]): Extra data to be injected into the template.

        Returns:
            str: The rendered system prompt.

        Raises:
            FileNotFoundError: If the template file is not found.
        """
        
        # If no template path is provided, use a default hard-coded path
        if template_path is None:
            # Assume the template file is in the prompts/ folder in the same directory as agent.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(current_dir, 'prompts', 'default_agent_prompt.md')
        try:
            # Set up Jinja2 environment to load templates from the file system
            template_dir = os.path.dirname(template_path)
            template_filename = os.path.basename(template_path)

            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                trim_blocks=True, # Automatically remove the first newline after a template tag
                lstrip_blocks=True # Automatically remove leading spaces before a template tag
            )
            
            template = env.get_template(template_filename)
        except jinja2.TemplateNotFound:
            raise FileNotFoundError(f"Prompt template not found at: {template_path}")
        
        plain_tools = []
        agent_tools = []
        for tool in self.tools.values():
            if getattr(tool, 'is_agent_tool', False):
                agent_tools.append(tool)
            else:
                plain_tools.append(tool)

        # Prepare data to pass to the template
        template_data = {
            "agent_name": self.name,
            "agent_description": self.description,
            "plain_tools": plain_tools, # Pass plain tools
            "agent_tools": agent_tools, # Pass Agent tools
            "tools": list(self.tools.values()), # Still pass the full list of tools for future use
            "target_language": self.target_lang
        }
        
        if extra_context:
            template_data.update(extra_context)
        
        # Render the template
        base_prompt = template.render(template_data)

        if self.optimize_tool_call:
            # If tool call optimization is enabled, append the tool call prompt
            tool_call_prompt_path = os.path.join(os.path.dirname(template_path), 'tool_call.md')
            try:
                with open(tool_call_prompt_path, 'r', encoding='utf-8') as f:
                    tool_call_prompt = f.read()
                return base_prompt + "\n" + tool_call_prompt
            except FileNotFoundError:
                # Handle case where tool_call.md is not found, maybe log a warning
                pass
        
        return base_prompt

    def _execute_tool(self, tool_call: Dict[str, Any]) -> Any:
        """Executes a tool call.

        Args:
            tool_call (Dict[str, Any]): The tool call object from the language model.

        Returns:
            Any: The result of the tool execution, or an error message string.
        """
        tool_name = tool_call.function.name
        tool_to_run = self.tools.get(tool_name)
        
        if not tool_to_run:
            return f"Error: Tool '{tool_name}' not found."
            
        try:
            tool_args = json.loads(tool_call.function.arguments)
            return tool_to_run.execute(**tool_args)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def run(self, stream: bool = False, resume: bool = False, **kwargs) -> Union[str, Iterator[Event]]:
        """Runs the main loop of the Agent.

        Args:
            stream (bool): If True, returns an event generator for real-time output.
                           If False, blocks until the task is complete and returns the final string.
            resume (bool): If True, continues from the existing history instead of resetting.
            **kwargs: Input parameters required to start the Agent.

        Returns:
            Union[str, Iterator[Event]]: The final result or the event stream.
        """
        if stream:
            return self._run_stream(resume=resume, **kwargs)
        else:
            # For non-streaming, we can simulate a simple event handler internally
            final_answer = ""
            for event in self._run_stream(resume=resume, **kwargs):
                if event.type == "end":
                    final_answer = event.payload.get("final_answer", "")
            return final_answer

    def _run_stream(self, resume: bool = False, **kwargs) -> Iterator[Event]:
        """Runs the main loop of the Agent as an event generator.

        This is the core method that drives the agent's think-act cycle. It
        communicates with the language model, executes tools, and yields
        events to report its progress.

        Args:
            resume (bool): If True, continues from the existing history.
            **kwargs: The input parameters for the task.

        Yields:
            Iterator[Event]: A stream of events representing the agent's activity.
        """
        # Only reset history if it's a new run
        if not resume:
            self.reset()
            # 1. Construct initial input and yield start event
            initial_prompt = (
                "Task started. Here are your input parameters:\n"
                + json.dumps(kwargs, indent=2)
                + "\nNow, begin your work."
            )
            self.history.append({"role": "user", "content": initial_prompt})
            yield Event(f"Agent:{self.name}", "start", kwargs)
        else:
            # If resuming, just yield a resume event
            yield Event(f"Agent:{self.name}", "resume", {"history_length": len(self.history)})
        # 2. "Think-Act" loop
        for step in range(self.max_steps):
            yield Event(f"Agent:{self.name}", "step", {"current_step": step + 1})

            # 3. Think: Call LLM
            llm_params = {
                "model": self.model_id,
                "messages": self.history,
                "stream": True
            }
            if not self.optimize_tool_call:
                llm_params["tools"] = self._api_tools
                llm_params["tool_choice"] = "auto"
            
            response_stream = self._client.chat.completions.create(**llm_params)

            # 4. Reassemble response from the stream
            full_response_content = ""
            full_reasoning_content = ""
            tool_calls_in_progress = []
            
            if self.optimize_tool_call:
                parser = IncrementalXmlParser(root_tag="response")
                in_tool_call = False

                def on_enter(tag, attrs):
                    nonlocal in_tool_call
                    if tag == 'tool_call':
                        in_tool_call = True
                        tool_calls_in_progress.append({"function": {"name": "", "arguments": ""}})

                def on_exit(tag):
                    nonlocal in_tool_call
                    if tag == 'tool_call':
                        in_tool_call = False

                parser.on_enter_tag = on_enter
                parser.on_exit_tag = on_exit
                
                def handle_tool_name(name_chunk):
                    if tool_calls_in_progress:
                        tool_calls_in_progress[-1]["function"]["name"] += name_chunk

                def handle_tool_args(args_chunk):
                    if tool_calls_in_progress:
                        tool_calls_in_progress[-1]["function"]["arguments"] += args_chunk
                
                def handle_root_text(text_chunk):
                    yield Event(f"Agent:{self.name}", "content_stream", {"content": text_chunk})

                parser.register_streaming_callback("tool_name", handle_tool_name)
                parser.register_streaming_callback("parameter", handle_tool_args)
                parser.register_streaming_callback(IncrementalXmlParser.ROOT, handle_root_text)

                for chunk in response_stream:
                    try:
                        delta = chunk.choices[0].delta
                    except:
                        continue
                    
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        full_reasoning_content += delta.reasoning_content
                        yield Event(f"Agent:{self.name}", "reasoning_stream", {"content": delta.reasoning_content})

                    if delta and delta.content:
                        full_response_content += delta.content
                        parser.feed(delta.content.encode('utf-8'))
                parser.close()

            else: # Original OpenAI tools handling
                for chunk in response_stream:
                    try:
                        delta = chunk.choices[0].delta
                    except:
                        continue
                    
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        full_reasoning_content += delta.reasoning_content
                        yield Event(f"Agent:{self.name}", "reasoning_stream", {"content": delta.reasoning_content})

                    if delta.content:
                        full_response_content += delta.content
                        yield Event(f"Agent:{self.name}", "content_stream", {"content": delta.content})
                    
                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            if tool_call_chunk.index >= len(tool_calls_in_progress):
                                tool_calls_in_progress.append({"id": f"call_{tool_call_chunk.index}", "type": "function", "function": {"name": "", "arguments": ""}})
                            
                            func = tool_calls_in_progress[tool_call_chunk.index]['function']
                            if tool_call_chunk.function.name:
                                func['name'] += tool_call_chunk.function.name
                            if tool_call_chunk.function.arguments:
                                func['arguments'] += tool_call_chunk.function.arguments
                            
                            yield Event(f"Agent:{self.name}", "tool_call_stream", {"index": tool_call_chunk.index, "delta": tool_call_chunk.function.dict()})

            # Assemble the complete message to add to history
            assembled_message = {"role": "assistant"}
            if full_response_content:
                assembled_message["content"] = full_response_content
            
            if tool_calls_in_progress:
                valid_tool_calls = []
                for i, tc in enumerate(tool_calls_in_progress):
                    func = tc.get('function', {})
                    if func.get('name') and func.get('arguments'):
                        try:
                            # Validate JSON arguments
                            json.loads(func['arguments'])
                            valid_tool_calls.append({
                                "id": tc.get("id", f"call_{i}"),
                                "type": "function",
                                "function": func
                            })
                        except json.JSONDecodeError:
                            continue # Skip invalid tool calls
                
                if valid_tool_calls:
                    assembled_message["tool_calls"] = valid_tool_calls
                    if not self.optimize_tool_call:
                         assembled_message["content"] = None
            
            self.history.append(assembled_message)
            # 5. Decision and Action
            if "tool_calls" in assembled_message:
                # Iterate through all tool calls
                for tool_call_data in assembled_message["tool_calls"]:
                    tool_name = tool_call_data['function']['name']
                    
                    # a. Special handling for end_task
                    if tool_name == "end_task":
                        task_result = json.loads(tool_call_data['function']['arguments'])
                        yield Event(f"Agent:{self.name}", "end", task_result)
                        return # End the generator

                    # b. Execute regular tool or Agent
                    tool_args = json.loads(tool_call_data['function']['arguments'])
                    yield Event(f"Agent:{self.name}", "decision", {"tool_name": tool_name, "tool_args": tool_args})
                    
                    tool_call_id = tool_call_data['id']
                    
                    # Execute the tool and handle possible event stream
                    execution_generator = self._execute_tool_from_dict(tool_call_data)
                    
                    tool_output = ""
                    # If it's a sub-agent, forward its events in real-time
                    if isinstance(execution_generator, Iterator):
                        for sub_event in execution_generator:
                            yield sub_event # Forward in real-time
                            # Capture the sub-agent's final answer as tool output
                            if sub_event.type == 'end' and sub_event.payload.get('final_answer'):
                                tool_output = sub_event.payload['final_answer']
                            if sub_event.type == 'end' and sub_event.payload.get('error'):
                                tool_output = sub_event.payload['error']
                    else: # If it's a normal tool
                        tool_output = execution_generator

                    yield Event(f"Agent:{self.name}", "tool_result", {"tool_name": tool_name, "output": tool_output})
                    
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": str(tool_output)
                    })
                continue
            else: # If the LLM replies directly without calling a tool
                yield Event(f"Agent:{self.name}", "thinking", {"content": full_response_content})
                # If the model responds directly, prompt it to use end_task to formalize the completion.
                self.history.append({
                    "role": "user",
                    "content": "You have provided a direct answer. If this is the final answer, please call the `end_task` tool to properly conclude the task. Do not add any commentary."
                })
                continue
        # If the loop finishes without completion
        final_message = f"Error: Agent '{self.name}' failed to complete the task within {self.max_steps} steps."
        yield Event(f"Agent:{self.name}", "error", {"message": final_message})
        yield Event(f"Agent:{self.name}", "end", {"error": final_message})
        return
    
    def _execute_tool_from_dict(self, tool_call_dict: Dict) -> Any:
        """Executes a tool. If the tool is an Agent, returns its event generator.

        Args:
            tool_call_dict (Dict): The tool call dictionary.

        Returns:
            Any: The result of the tool execution. This can be a direct result
                 or an iterator of events if the tool is another agent.
        """
        name = tool_call_dict['function']['name']
        args = json.loads(tool_call_dict['function']['arguments'])
        tool: Optional[Tool] = self.tools.get(name)

        if not tool:
            return f"Error: Tool '{name}' not found."
        
        try:
            # If it's an Agent tool, it will return a generator
            if tool.is_agent_tool:
                # Ensure it's called in streaming mode
                return tool.execute(stream=True, **args)
            else: # Otherwise, it will return a direct result
                return tool.execute(**args)
        except Exception as e:
            return f"Error executing tool '{name}': {e}"

    def as_tool(self) -> Tool:
        """Wraps the entire Agent instance into a Tool.

        This allows the agent to be called by other agents.

        Returns:
            Tool: A Tool instance that encapsulates this agent.
        """
        # Dynamically create a wrapper function
        def agent_runner(stream: bool = False, **kwargs):
            # On each call, create a new Agent instance to ensure state isolation
            agent_instance = Agent(
                name=self.name,
                description=self.description,
                input_parameters=self.input_parameters,
                tools=self.original_tools, # Ensure isolation
                endpoint=self.endpoint,
                model_id=self.model_id,
                max_steps=self.max_steps,
                optimize_tool_call=self.optimize_tool_call
            )
            return agent_instance.run(stream=stream, **kwargs)

        # Fake a function so the Tool class can parse it
        # This step is a bit hacky, but very effective
        agent_runner.__name__ = self.name
        agent_runner.__doc__ = f'An Agent: {self.description}'
        
        # Dynamically build the function signature
        from inspect import Parameter, Signature
        params = [
            Parameter(name=p['name'], kind=Parameter.POSITIONAL_OR_KEYWORD) 
            for p in self.input_parameters
        ]
        agent_runner.__signature__ = Signature(params)

        return Tool(func=agent_runner, is_agent_tool=True)

    def get_state(self) -> Dict[str, Any]:
        """Gets the current state of the agent.

        Returns:
            A dictionary containing the agent's history.
        """
        return {
            "history": self.history
        }

    def set_state(self, state: Dict[str, Any]):
        """Sets the state of the agent from a state dictionary.

        Args:
            state: A dictionary containing the agent's state.
        """
        self.history = state.get("history", [{"role": "system", "content": self.system_prompt}])

    def reset(self):
        """Resets the agent's history.

        This clears the conversation history, preparing the agent for a new run.
        """
        self.history = [{"role": "system", "content": self.system_prompt}]
