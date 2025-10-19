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
        parameters: Optional[List[Dict[str, Any]]] = None,
        is_agent_tool: bool = False,
        is_group_tool: bool = False
    ):
        """
        Creates a tool instance.

        Args:
            func (Callable): The Python function to be wrapped as a tool.
            name (Optional[str]): Optional. Manually specify the tool's name. If None, the function name is used.
            description (Optional[str]): Optional. Manually specify the tool's description. If None, it's parsed from the function's docstring.
            parameters (Optional[List[Dict[str, Any]]]): Optional. Manually specify the tool's parameters. If None, they are parsed from the function's signature.
        """
        self.func = func
        
        # 1. Use our powerful analysis function to parse metadata
        analysis = analyze_tool_function(func)
        
        # 2. Set the core properties of the tool, allowing for manual override
        self.name: str = name or func.__name__
        self.description: str = description or analysis.get('docstring', 'No description provided.')
        self.parameters: List[Dict[str, Any]] = parameters or analysis.get('parameters', [])
        self.is_agent_tool = is_agent_tool
        self.is_group_tool = is_group_tool
    
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


import os
import tempfile
import shutil
import json
from .mutilmodal import get_input_processor


class Workspace:
    """Manages a shared workspace for agents, providing sandboxed file tools.

    This class creates a secure directory that agents can use to read, write,
    and list files. It can manage either a user-specified directory or a
    temporary one that is automatically cleaned up.

    When integrated with a `Group`, the file manipulation methods (`list_files`,
    `read_file`, `write_file`) are exposed as tools to all agents in that group,
    ensuring they all operate within the same file system context.

    Attributes:
        path (str): The absolute path to the workspace directory.
    """
    def __init__(self, path: Optional[str] = None):
        """Initializes the Workspace.

        If a path is provided, it will be used as the workspace directory.
        If the path does not exist, it will be created. If no path is
        provided, a new temporary directory will be created by the system.

        Args:
            path (Optional[str]): The directory path for the workspace.
                If None, a temporary directory is created.
        """
        if path:
            self.path = os.path.abspath(path)
            os.makedirs(self.path, exist_ok=True)
            self._is_temp = False
        else:
            self.path = tempfile.mkdtemp()
            self._is_temp = True

    def _resolve_path(self, file_path: str) -> str:
        """Resolves a relative path to an absolute path within the workspace, preventing directory traversal."""
        # Normalize the path to prevent '..' tricks
        abs_path = os.path.abspath(os.path.join(self.path, file_path))
        if not abs_path.startswith(self.path):
            raise ValueError("Access denied: Path is outside the workspace.")
        return abs_path

    def list_files(self, sub_path: str = '.') -> str:
        """Lists files and directories within a sub-path of the workspace.

        Args:
            sub_path (str): The relative path from the workspace root
                to list files from. Defaults to the workspace root.

        Returns:
            str: A newline-separated string of file and directory names.
        """
        target_path = self._resolve_path(sub_path)
        return "\n".join(os.listdir(target_path))

    def read_file(self, file_path: str, agent: Any, chunk_size: int = 4000, overlap: int = 200) -> str:
        """
        Call this tool to read a file from the workspace and load its content into your memory (history).
        This tool can handle any file type, including text, code, and images, as it uses a multimodal processor.
        For large text files, the content will be automatically split into manageable chunks and loaded sequentially.

        Args:
            file_path (str): The relative path of the file you want to read.
            agent (Any): The agent instance to whose history the file will be added.
            chunk_size (int): The size of each text chunk for large files.
            overlap (int): The overlap between consecutive text chunks.

        Returns:
            str: A confirmation message indicating the file has been loaded.
        """
        if not agent or not hasattr(agent, 'add_file'):
            return "Error: A valid agent instance with an `add_file` method must be provided."

        try:
            abs_path = self._resolve_path(file_path)
            # Delegate the file reading and history management to the agent's `add_file` method
            agent.add_file(abs_path, chunk_size=chunk_size, overlap=overlap)
            return f"File '{file_path}' has been successfully read and added to the agent's history."
        except FileNotFoundError:
            return f"Error: File '{file_path}' not found."
        except Exception as e:
            return f"Error processing file '{file_path}': {e}"

    def write_file(self, file_path: str, content: str) -> str:
        """Writes content to a file within the workspace.

        If the file or its parent directories do not exist, they will be
        created. If the file already exists, its content will be overwritten.

        Args:
            file_path (str): The relative path of the file to write to.
            content (str): The content to write to the file.

        Returns:
            str: A confirmation message indicating success.
        """
        abs_path = self._resolve_path(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"File '{file_path}' written successfully."

    def get_tools(self) -> List['Tool']:
        """Returns a list of Tool instances for interacting with the workspace.

        These tools are generated from the workspace's own methods and are
        sandboxed to operate only within the workspace directory.

        Returns:
            List[Tool]: A list of `Tool` objects for `list_files`,
                `read_file`, and `write_file`.
        """
        return [
            Tool(self.list_files),
            Tool(self.read_file),
            Tool(self.write_file)
        ]

    def cleanup(self):
        """Removes the workspace directory if it was created as a temporary directory.

        This method should be called after the workspace is no longer needed
        to ensure system resources are freed. It has no effect if the
        workspace was initialized with a specific path.
        """
        if self._is_temp and os.path.exists(self.path):
            shutil.rmtree(self.path)

    def __repr__(self) -> str:
        return f"Workspace(path='{self.path}')"
