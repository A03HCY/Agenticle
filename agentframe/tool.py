from typing import Callable, Any, Dict, Optional, List
from .utils import analyze_tool_function 


class Tool:
    """
    Agent 可以使用的工具的基类。

    这个类可以通过两种方式使用：
    1. (推荐) 直接用一个带有良好文档字符串的函数来实例化，Tool 将自动解析其元数据。
       示例: `my_tool = Tool(my_function)`
    2. (适用于复杂情况) 继承这个类，并重写 `execute` 方法。
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_agent_tool: bool = False
    ):
        """
        创建一个工具实例。

        Args:
            func (Callable): 要被封装为工具的 Python 函数。
            name (Optional[str]): 可选。手动指定工具的名称。如果为 None，则使用函数名。
            description (Optional[str]): 可选。手动指定工具的描述。如果为 None，则自动从函数的文档字符串中解析。
        """
        self.func = func
        
        # 1. 使用我们强大的分析函数来解析元数据
        analysis = analyze_tool_function(func)
        
        # 2. 设置工具的核心属性，允许手动覆盖
        self.name: str = name or func.__name__
        self.description: str = description or analysis.get('docstring', 'No description provided.')
        self.parameters: List[Dict[str, Any]] = analysis.get('parameters', [])
        self.is_agent_tool = is_agent_tool
    
    @property
    def info(self) -> Dict[str, Any]:
        """
        生成一个符合 OpenAI Function Calling 规范的工具描述字典。
        
        Returns:
            一个可以被直接序列化为 JSON 并发送给 LLM API 的字典。
        """
        # 1. 构建 'properties' 和 'required' 列表
        json_schema_properties = {}
        required_params = []
        # 简单的 Python 类型到 JSON Schema 类型的映射
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
        self.execute(**kwargs)
        
    def execute(self, **kwargs: Any) -> Any:
        """
        执行工具的核心逻辑。

        Args:
            **kwargs: 从 Agent 传入的参数，键是参数名，值是参数值。

        Returns:
            工具函数的执行结果。
        """
        return self.func(**kwargs)

    def __repr__(self) -> str:
        return f"Tool(name='{self.name}')"


class EndTaskTool(Tool):
    """
    一个特殊的工具，Agent 调用它来表示任务已完成并返回最终答案。
    """
    def __init__(self):
        # 这个工具的函数签名定义了 Agent 的最终输出结构
        def end_task(final_answer: str) -> None:
            """
            当你已经获得了最终答案并准备好结束任务时，调用此工具。
            Args:
                final_answer (str): 最终要返回给用户或上层代理的完整答案。
            """
            # 这个函数实际上不会被执行，它只是用来提供签名和文档。
            pass
        
        # 调用父类的构造函数，并传入这个伪函数
        super().__init__(
            func=end_task,
            name="end_task",
            description="当你完成了所有步骤并准备好向用户提供最终答案时，调用此函数。"
        )
    def execute(self, **kwargs: Any) -> Any:
        # 这个执行函数也不做任何事，因为它的调用会在 Agent 循环中被特殊处理。
        # 它仅仅返回参数，以防万一在非预期的流程中被调用。
        return kwargs