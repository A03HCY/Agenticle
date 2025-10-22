import os
from typing import List, Dict, Any, Iterator

from agenticle.schema import Endpoint, Response

class OpenAICompatService:
    def __init__(self, endpoint: Endpoint):
        from openai import OpenAI
        self.endpoint = endpoint
        self._client: OpenAI = None
        self._init_client()

    def _init_client(self):
        from openai import OpenAI
        """Initializes the OpenAI client with the provided API key and base URL."""
        # Temporarily store the original API key if it exists in environment
        prev_api_key = os.environ.get('OPENAI_API_KEY')
        
        # Set the API key from the endpoint for client initialization
        os.environ['OPENAI_API_KEY'] = self.endpoint.api_key
        
        # Initialize the OpenAI client
        self._client = OpenAI(api_key=self.endpoint.api_key, base_url=self.endpoint.base_url)
        
        # Restore the original API key if it was set
        if prev_api_key is not None:
            os.environ['OPENAI_API_KEY'] = prev_api_key
        else:
            # If it wasn't set, remove it to clean up
            if 'OPENAI_API_KEY' in os.environ:
                del os.environ['OPENAI_API_KEY']

    def completion(self, model: str, messages: List[Dict[str, Any]], stream: bool, **kwargs) -> Iterator[Response]:
        """
        Calls the OpenAI chat completions API and yields standardized Response objects.
        """
        llm_params = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs
        }
        
        response_stream = self._client.chat.completions.create(**llm_params)
        
        for chunk in response_stream:
            try:
                delta = chunk.choices[0].delta
            except (AttributeError, IndexError):
                continue
            
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                yield Response(thinking=delta.reasoning_content)

            if delta.content:
                yield Response(content=delta.content)
            
            if delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    # Yield partial tool call information directly
                    yield Response(tool_calls=[{"index": tool_call_chunk.index, "delta": tool_call_chunk.function.dict()}])
