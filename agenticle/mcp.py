from sseclient    import SSEClient
from urllib.parse import urlparse
from typing       import Dict, Any
from .tool        import Tool
import threading
import requests
import queue
import json
import subprocess

class StdioClient:
    """A client for communicating with a subprocess via standard I/O."""
    def __init__(self, command:str) -> None:
        """
        Initializes the StdioClient and starts the subprocess.

        Args:
            command (str): The command to execute to start the subprocess.
        """
        self.command = command
        self.process: subprocess.Popen = subprocess.Popen(self.command.split(' '), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.stdin = self.process.stdin
        self.stdout = self.process.stdout


class LegacyClient:
    """
    A client for communicating with an MCP server using older protocols
    like SSE or stdio for transport.
    """
    def __init__(self, endpoint:str|list, name='mcp', version='0.1.0'):
        """
        Initializes the LegacyClient.

        Args:
            endpoint (str | list): The server endpoint. Can be an HTTP URL for SSE
                                   or a command string/list for stdio.
            name (str): The name of this client.
            version (str): The version of this client.
        """
        if isinstance(endpoint, list):
            endpoint = ' '.join(endpoint)
        self._method: str = None
        self.client_name = name
        self.client_version = version
        self.server_name = None
        self.server_version = None
        self.base_url = self._parse_base_url(endpoint)
        self.session = None
        self.endpoint = endpoint
        self.endpoint_ready = threading.Event()
        self.response_queues = {}
        self.lock = threading.Lock()
        self._running = True
        self._next_id = 0  # 自增ID计数器
        self._stdio: StdioClient = None

        # 启动消息接收线程
        if self._method == 'sse':
            self.recv_thread = threading.Thread(target=self._sse_recv_loop, daemon=True)
            self.recv_thread.start()
        if self._method == 'stdio':
            try:
                self._stdio = StdioClient(self.endpoint)
                self.endpoint_ready.set()
            except:
                self._running = False
                raise Exception(f"Failed to start stdio client: {self.endpoint}")
        try:
            self._init_client()
        except:
            self._running = False
    
    def _init_client(self):
        data = self.post(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": self.client_name,
                    "version": self.client_version,
                }
            }
        )
        data = data.get('result', {}).get("serverInfo", {})
        self.server_name = data.get("name")
        self.server_version = data.get("version")
        self.post(
            method="notifications/initialized",
            wait_for_response=False
        )

    def _parse_base_url(self, endpoint):
        """Parse the base URL from the endpoint."""
        if not 'http' in endpoint:
            self._method = 'stdio'
            return ''
        self._method = 'sse'
        parsed = urlparse(endpoint)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _sse_recv_loop(self):
        messages = SSEClient(self.endpoint)
        
        event = None
        for msg in messages:
            if not self._running:
                break

            if not msg.data:
                event = msg.event
                continue

            if event == "endpoint" or 'session_id' in msg.data:
                self.session = msg.data
                self.endpoint_ready.set()
                event = msg.event
                continue

            try:
                data = json.loads(msg.data)
                msg_id = data.get("id")
            except json.JSONDecodeError:
                continue

            with self.lock:
                if msg_id in self.response_queues:
                    self.response_queues[msg_id].put(data)
                else:
                    print(f"Unmatched response (id={msg_id})")
    
    def _stdio_recv(self):
        if not self._running: return
        try:
            data = self._stdio.stdout.readline()
        except:
            self._running = False
            return
        if not data: return self._stdio_recv()
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return
        return data

    def post(self, method=None, params=None, timeout=10, wait_for_response=True):
        self.endpoint_ready.wait()

        # 构造请求数据
        if method is None:
            raise ValueError("Either method or data must be provided")

        data = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }


        # 注册响应队列
        if wait_for_response:
            # 生成自增ID（线程安全）
            with self.lock:
                request_id = self._next_id
                data['id'] = request_id
                self._next_id += 1
            with self.lock:
                self.response_queues[request_id] = queue.Queue()

        # 构建完整URL
        full_url = f"{self.base_url}{self.session}"

        try:
            if self._method == 'sse':
                response = requests.post(
                    full_url,
                    json=data,
                    timeout=5
                )
            elif self._method == 'stdio':
                self._stdio.stdin.write(json.dumps(data) + '\n')
                self._stdio.stdin.flush()
                if wait_for_response:
                    data = self._stdio_recv()
                    return data
                return {"status": "sent"}
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Request failed: {str(e)}")

        if not wait_for_response:
            return {"status": "sent", "code": response.status_code}

        try:
            with self.lock:
                q = self.response_queues.get(request_id)
            
            if q is None:
                raise ValueError("Response queue not found")

            response_data = q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"Response timeout (id={request_id})")
        finally:
            with self.lock:
                if request_id in self.response_queues:
                    del self.response_queues[request_id]

        return response_data
    
    def list_tools(self):
        """Lists all available tools from the server."""
        return self.post(
            method="tools/list",
            params={}
        ).get('result', {}).get("tools", [])
    
    def call_tool(self, tool_name, input_data: dict={}):
        """
        Calls a tool on the server with the given input data.

        Args:
            tool_name (str): The name of the tool to call.
            input_data (dict): The arguments for the tool.

        Returns:
            The result of the tool execution.
        """
        return self.post(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": input_data
            },
            timeout=None
        )

    def close(self):
        """Stops the client and terminates background threads."""
        self._running = False
    

class StreamHttpClient:
    """
    A client for communicating with an MCP server using the modern,
    streamable HTTP POST protocol.
    """
    def __init__(self, endpoint:str|list, name='mcp', version='0.1.0'):
        """
        Initializes the StreamHttpClient.

        Args:
            endpoint (str | list): The server endpoint URL.
            name (str): The name of this client.
            version (str): The version of this client.
        """
        self.endpoint = endpoint
        self.client_name = name
        self.client_version = version
        self.server_name = None
        self.server_version = None
        self.protocol_version: str = "2025-05-16"
        self.session = None
        self._next_id = 0  # 自增ID计数器

        self._initialize()
    
    def _post_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(self.endpoint, json=payload, headers={"Accept": "application/json"})
        if r.status_code == 204 or not r.content:
            return {}
        r.raise_for_status()
        return r.json()

    def _initialize(self) -> None:
        self.session = requests.Session()
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            },
        }
        self._next_id += 1
        r = self._post_json(init_req)
        if "error" in r:
            raise RuntimeError(f"Initialize error: {r['error']}")
        
        server_info = r.get('result', {}).get("serverInfo", {})
        self.server_name = server_info.get("name")
        self.server_version = server_info.get("version")

        self._post_json({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self) -> list:
        """Lists all available tools from the server."""
        req = {"jsonrpc": "2.0", "id": self._next_id, "method": "tools/list", "params": {}}
        self._next_id += 1
        res = self._post_json(req)
        return res.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Calls a tool on the server and streams the response.

        Args:
            tool_name (str): The name of the tool to call.
            arguments (Dict[str, Any]): The arguments for the tool.

        Returns:
            A string containing the concatenated text from the tool's output.
        """
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        self._next_id += 1
        
        with self.session.post(self.endpoint, json=req, headers={"Accept": "application/json"}, stream=True) as resp:
            resp.raise_for_status()
            collected_text = []
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                chunk = json.loads(line)
                if "stream" in chunk:
                    continue
                if "error" in chunk:
                    raise RuntimeError(chunk["error"]["message"])
                if "result" in chunk:
                    for item in chunk["result"]["content"]:
                        if item["type"] == "text":
                            collected_text.append(item["text"])
            return "\n".join(collected_text)

    def close(self) -> None:
        """Closes the HTTP session."""
        if self.session:
            self.session.close()
            self.session = None


class MCP:
    """
    A client for the Model Context Protocol (MCP) that wraps different
    transport clients (Legacy, StreamHttpClient) and exposes server
    functionalities like listing and calling tools as native Agenticle Tools.
    """
    def __init__(self, endpoint:str|list, name='mcp', version='0.1.0', method='auto'):
        """
        Initializes the MCP client.

        It automatically detects the appropriate communication method (stdio, sse, http)
        based on the endpoint format.

        Args:
            endpoint (str | list): The server endpoint. Can be an HTTP URL or a
                                   command string/list for a local subprocess.
            name (str): The name of this client.
            version (str): The version of this client.
            method (str): The communication method. Defaults to 'auto'.
        """
        if isinstance(endpoint, list):
            endpoint = ' '.join(endpoint)
        self.method = self._parse_method(endpoint)
        if self.method in ['sse', 'stdio']:
            self.client = LegacyClient(endpoint, name, version)
        else:
            self.client = StreamHttpClient(endpoint, name, version)
        
        self.funtion_data = {}
    
    def _parse_method(self, endpoint: str):
        if endpoint.endswith('/sse'):
            return 'sse'
        if endpoint.startswith('http'):
            return 'streamable_http'
        return 'stdio'
    
    def list_tools(self) -> list[Tool]:
        """
        Fetches the list of tools from the MCP server and wraps them as
        Agenticle Tool objects.

        Returns:
            A list of Tool instances that can be used by an Agent.
        """
        tool_data = self.client.list_tools()
        tools = []
        for tool_info in tool_data:
            tool_name = tool_info['name']
            
            def create_tool_func(name):
                return lambda **kwargs: self.call_tool(name, kwargs)

            tool_func = create_tool_func(tool_name)
            
            # Extract parameters from inputSchema
            schema_params = tool_info.get('inputSchema', {}).get('properties', {})
            required_params = tool_info.get('inputSchema', {}).get('required', [])
            
            tool_params = []
            for param_name, param_info in schema_params.items():
                tool_params.append({
                    "name": param_name,
                    "description": param_info.get('description', ''),
                    "annotation": param_info.get('type', 'string'),
                    "required": param_name in required_params
                })

            tool = Tool(
                func=tool_func,
                name=tool_name,
                description=tool_info['description'],
                parameters=tool_params
            )
            tools.append(tool)
        return tools
    
    def call_tool(self, tool_name, input_data: dict={}):
        """
        Calls a tool on the MCP server.

        This method is typically not called directly but is used by the
        Tool objects created by `list_tools`.

        Args:
            tool_name (str): The name of the tool to call.
            input_data (dict): The arguments for the tool.

        Returns:
            The result of the tool execution from the server.
        """
        return self.client.call_tool(tool_name, input_data)
    
    def close(self):
        """Closes the connection to the MCP server."""
        self.client.close()
