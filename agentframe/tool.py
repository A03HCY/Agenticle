from typing import Callable, Any, Dict, Optional, List
from .utils import analyze_tool_function 


class Tool:
    """
    Base class for tools that can be used by an Agent.

    This class can be used in two ways:
    1. (Recommended) Instantiate directly with a well-documented function, and Tool will automatically parse its metadata.
       Example: `my_tool = Tool(my_function)`
    2. (For complex cases) Inherit from this class and override the `execute` method.
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_agent_tool: bool = False
    ):
        """
        Creates a tool instance.

        Args:
            func (Callable): The Python function to be wrapped as a tool.
            name (Optional[str]): Optional. Manually specify the tool's name. If None, the function name is used.
            description (Optional[str]): Optional. Manually specify the tool's description. If None, it's parsed from the function's docstring.
        """
        self.func = func
        
        # 1. Use our powerful analysis function to parse metadata
        analysis = analyze_tool_function(func)
        
        # 2. Set the core properties of the tool, allowing for manual override
        self.name: str = name or func.__name__
        self.description: str = description or analysis.get('docstring', 'No description provided.')
        self.parameters: List[Dict[str, Any]] = analysis.get('parameters', [])
        self.is_agent_tool = is_agent_tool
    
    @property
    def info(self) -> Dict[str, Any]:
        """
        Generates a tool description dictionary compliant with the OpenAI Function Calling specification.
        
        Returns:
            A dictionary that can be directly serialized to JSON and sent to the LLM API.
        """
        # 1. Build 'properties' and 'required' list
        json_schema_properties = {}
        required_params = []
        # Simple mapping from Python types to JSON Schema types
        py_to_json_type_map = {
            'str': 'string',
            'int': 'integer',
            'float': 'number',
            'bool': 'boolean',
            'list': 'array',
            'dict': 'object'
        }
        for param in self.parameters:
            param_name = param['name']
            
            param_type = py_to_json_type_map.get(param.get('annotation', 'str'), 'string')
            
            json_schema_properties[param_name] = {
                "type": param_type,
                "description": param.get('description', '')
            }
            
            if param.get('required', False):
                required_params.append(param_name)
        
        if not self.description.startswith('A tool: ') and not self.description.startswith('An Agent: '):
            self.description = f'A tool: {self.description}'
                
        tool_info = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": json_schema_properties,
                }
            }
        }
        
        if required_params:
            tool_info['function']['parameters']['required'] = required_params
            
        return tool_info
    
    def __call__(self, **kwargs):
        """Allows the tool instance to be called like a function."""
        return self.execute(**kwargs)
        
    def execute(self, **kwargs: Any) -> Any:
        """
        Executes the core logic of the tool.

        Args:
            **kwargs: Parameters passed from the Agent, where keys are parameter names and values are their values.

        Returns:
            The execution result of the tool's function.
        """
        return self.func(**kwargs)

    def __repr__(self) -> str:
        """Provides a string representation of the Tool instance."""
        return f"Tool(name='{self.name}')"


class EndTaskTool(Tool):
    """
    A special tool that an Agent calls to indicate the task is complete and to return the final answer.
    """
    def __init__(self):
        """Initializes the EndTaskTool."""
        # The function signature of this tool defines the final output structure of the Agent.
        def end_task(final_answer: str) -> None:
            """
            Call this tool when you have the final answer and are ready to end the task.
            Args:
                final_answer (str): The complete answer to be returned to the user or the parent agent.
            """
            # This function is not actually executed; it's just for providing the signature and documentation.
            pass
        
        # Call the parent constructor with this pseudo-function
        super().__init__(
            func=end_task,
            name="end_task",
            description="Call this function when you have completed all steps and are ready to provide the final answer to the user."
        )
    def execute(self, **kwargs: Any) -> Any:
        # This execute function also does nothing, as its call is specially handled in the Agent loop.
        # It merely returns the arguments in case it's called in an unexpected flow.
        return kwargs
