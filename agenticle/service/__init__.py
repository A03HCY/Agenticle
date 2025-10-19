import json
from typing import Dict, Type, Iterator

from agenticle.schema import Endpoint, Response
from agenticle.service.openai_compat import OpenAICompatService
from agenticle.utils.parser import IncrementalXmlParser


_supported_services: Dict[str, Type[OpenAICompatService]] = {
    'openai_compat': OpenAICompatService
}

class Service:
    """
    A factory class for creating and managing different language model services.
    """
    def __init__(self, endpoint: Endpoint, service_type: str =None , optimize_tool_call: bool = False):
        if service_type is None:
            service_type = endpoint.platform
        if service_type not in _supported_services:
            raise ValueError(f"Service type '{service_type}' is not supported. Supported types are: {list(_supported_services.keys())}")
        
        self.server = _supported_services[service_type](endpoint)
        self.optimize_tool_call = optimize_tool_call
    
    def completion(self, *args, **kwargs) -> Iterator[Response]:
        """
        Calls the underlying service's completion method and processes the stream,
        optionally applying XML parsing for optimized tool calls.
        """
        response_stream = self.server.completion(*args, **kwargs)
        
        if self.optimize_tool_call:
            parser = IncrementalXmlParser(root_tag="response")
            tool_calls_in_progress = []
            current_thinking = ""
            current_content = ""

            def on_enter(tag, attrs):
                if tag == 'tool_call':
                    tool_calls_in_progress.append({"function": {"name": "", "arguments": ""}})

            def on_exit(tag):
                pass # No specific action on exit for now

            parser.on_enter_tag = on_enter
            parser.on_exit_tag = on_exit
            
            def handle_tool_name(name_chunk):
                if tool_calls_in_progress:
                    tool_calls_in_progress[-1]["function"]["name"] += name_chunk

            def handle_tool_args(args_chunk):
                if tool_calls_in_progress:
                    tool_calls_in_progress[-1]["function"]["arguments"] += args_chunk
            
            def handle_root_text(text_chunk):
                nonlocal current_content
                current_content += text_chunk
                yield Response(content=text_chunk)

            parser.register_streaming_callback("tool_name", handle_tool_name)
            parser.register_streaming_callback("parameter", handle_tool_args)
            parser.register_streaming_callback(IncrementalXmlParser.ROOT, handle_root_text)

            for response_obj in response_stream:
                if response_obj.thinking:
                    current_thinking += response_obj.thinking
                    yield Response(thinking=response_obj.thinking)
                
                if response_obj.content:
                    parser.feed(response_obj.content)
                
                # If there are tool calls from the underlying service (native tool calls)
            parser.close()
            # Note: When optimize_tool_call is True, native tool calls from the underlying service
            # are ignored here, as the expectation is that tool calls are parsed from XML content.
            # The agent's prompt for optimized tool calling should guide the model to output XML.

            # After the stream ends, yield a final response with accumulated XML tool calls if any
            if tool_calls_in_progress:
                valid_tool_calls = []
                for i, tc in enumerate(tool_calls_in_progress):
                    func = tc.get('function', {})
                    if func.get('name') and func.get('arguments'):
                        try:
                            json.loads(func['arguments'])
                            valid_tool_calls.append({
                                "id": tc.get("id", f"call_{i}"),
                                "type": "function",
                                "function": func
                            })
                        except json.JSONDecodeError:
                            continue
                if valid_tool_calls:
                    yield Response(tool_calls=valid_tool_calls)

        else: # No tool call optimization, just yield from the underlying service
            yield from response_stream
