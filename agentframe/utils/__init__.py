from typing           import Callable, Any, Dict, List
from docstring_parser import parse
import inspect

def get_function_details(func: Callable) -> Dict[str, Any]:
    """
    检查一个函数，并以结构化的形式返回其参数和文档字符串。

    Args:
        func (Callable): 需要被检查的目标函数。

    Returns:
        Dict[str, Any]: 一个包含 'parameters' 和 'docstring' 键的字典。
                        'parameters' 是一个列表，每个元素都是描述一个参数的字典。
                        'docstring' 是函数的文档字符串。
    """
    if not callable(func):
        raise TypeError("提供的对象不是一个可调用函数。")

    # 1. 获取文档字符串 (使用 inspect.getdoc 可以很好地处理缩进)
    docstring = inspect.getdoc(func) or "No docstring provided."
    
    # 2. 获取函数签名 (Signature)
    try:
        signature = inspect.signature(func)
    except (ValueError, TypeError):
        # 对于某些内置函数或C语言实现的函数，可能无法获取签名
        return {
            'parameters': "Could not retrieve parameters for this function.",
            'docstring': docstring
        }

    # 3. 遍历签名中的所有参数并提取信息
    parameters_details: List[Dict[str, Any]] = []
    for name, param in signature.parameters.items():
        param_info = {
            'name': name,
            'kind': str(param.kind.description),  # e.g., 'positional or keyword'
            'default': param.default if param.default is not inspect.Parameter.empty else 'N/A',
            'annotation': param.annotation.__name__ if hasattr(param.annotation, '__name__') \
                          and param.annotation is not inspect.Parameter.empty else 'N/A'
        }
        parameters_details.append(param_info)
        
    return {
        'parameters': parameters_details,
        'docstring': docstring
    }


def analyze_tool_function(func: Callable) -> Dict[str, Any]:
    """
    深度分析一个函数，结合其签名和 docstring-parser 的解析结果，
    返回每个参数的详细信息。能够自动识别 Google, reST, NumPy 等多种风格。
    """
    # 1. 使用 inspect 获取最可靠的签名信息和原始 docstring
    basic_details = get_function_details(func)
    original_docstring = basic_details.get('docstring', '')
    # 2. 使用 docstring-parser 解析文档字符串
    parsed_docstring = parse(original_docstring)
    
    
    # 3. 为快速查找，将解析出的参数描述转为字典
    param_descriptions = {
        param.arg_name: param.description for param in parsed_docstring.params
    }
    
    # 4. 组合函数的摘要描述
    summary_parts = []
    if parsed_docstring.short_description:
        summary_parts.append(parsed_docstring.short_description)
    if parsed_docstring.long_description:
        summary_parts.append(parsed_docstring.long_description)
    summary = "\n\n".join(summary_parts) if summary_parts else ""
    # 5. 合并来自签名和 docstring 的信息
    enhanced_parameters = []
    if isinstance(basic_details['parameters'], list):
        for param in basic_details['parameters']:
            param_name = param['name']
            
            enhanced_param = param.copy()
            
            # 从解析结果中获取描述
            enhanced_param['description'] = param_descriptions.get(
                param_name, "No description found in docstring."
            ).replace('\n', ' ')
            
            # “是否必需”的信息来源于签名的默认值，这是最可靠的
            enhanced_param['required'] = (param['default'] == 'N/A')
            
            enhanced_parameters.append(enhanced_param)
            
    return {
        'docstring': summary,
        'parameters': enhanced_parameters
    }