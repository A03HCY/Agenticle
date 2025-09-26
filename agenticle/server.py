import asyncio
import uuid
from typing import Dict, Any, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import json

from .agent import Agent
from .group import Group

# --- Globals ---
app = FastAPI(
    title="Agenticle API",
    description="A RESTful API for interacting with Agenticle Agents and Groups.",
    version="1.0.0"
)

# A simple in-memory registry for agents and groups
AGENT_REGISTRY: Dict[str, Union[Agent, Group]] = {}

# A simple in-memory store for async tasks
TASK_STORE: Dict[str, Dict[str, Any]] = {}


# --- Pydantic Models ---
class TaskRunRequest(BaseModel):
    agent_or_group_name: str
    input_data: Dict[str, Any]

class TaskCreationResponse(BaseModel):
    task_id: str
    status: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Any = None


# --- Helper Functions ---
def register(name: str, agent_or_group: Union[Agent, Group]):
    """Registers an Agent or Group to make it available to the API."""
    print(f"Registering '{name}'...")
    AGENT_REGISTRY[name] = agent_or_group

async def _run_task_async(task_id: str, name: str, input_data: Dict[str, Any]):
    """The background worker for running a task asynchronously."""
    try:
        agent_or_group = AGENT_REGISTRY[name]
        TASK_STORE[task_id]['status'] = 'running'
        
        # Run in non-streaming mode to get the final result
        result = agent_or_group.run(stream=False, **input_data)
        
        TASK_STORE[task_id]['status'] = 'completed'
        TASK_STORE[task_id]['result'] = result
    except Exception as e:
        TASK_STORE[task_id]['status'] = 'failed'
        TASK_STORE[task_id]['result'] = str(e)


# --- API Endpoints ---

@app.post("/v1/tasks/stream", summary="Run a task and stream events")
async def run_task_stream(request: TaskRunRequest):
    """
    Starts a task and immediately streams back Server-Sent Events (SSE).
    This is a blocking request that holds the connection open.
    """
    name = request.agent_or_group_name
    if name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"'{name}' not found in registry.")
    
    agent_or_group = AGENT_REGISTRY[name]

    async def event_generator():
        event_stream = agent_or_group.run(stream=True, **request.input_data)
        try:
            for event in event_stream:
                yield f"data: {json.dumps(event.__dict__)}\n\n"
                await asyncio.sleep(0.01) # Yield control to the event loop
        except asyncio.CancelledError:
            print("Client disconnected from stream.")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/v1/tasks", response_model=TaskCreationResponse, summary="Run a task asynchronously")
async def run_task_async(request: TaskRunRequest):
    """
    Starts a task in the background and immediately returns a task ID.
    Use the /v1/tasks/{task_id} endpoint to check the status and get the result.
    """
    name = request.agent_or_group_name
    if name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"'{name}' not found in registry.")

    task_id = str(uuid.uuid4())
    TASK_STORE[task_id] = {"status": "pending", "result": None}
    
    # Run the task in the background
    asyncio.create_task(_run_task_async(task_id, name, request.input_data))
    
    return TaskCreationResponse(task_id=task_id, status="pending")


@app.get("/v1/tasks/{task_id}", response_model=TaskStatusResponse, summary="Get task status and result")
async def get_task_status(task_id: str):
    """
    Retrieves the current status and result of an asynchronously started task.
    """
    if task_id not in TASK_STORE:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    return TaskStatusResponse(task_id=task_id, **TASK_STORE[task_id])


def start_server(host: str = "127.0.0.1", port: int = 8000):
    """
    Starts the Agenticle API server.
    
    Note: Agents and Groups must be registered using `agenticle.server.register()`
    before the server is started.
    """
    print(f"Starting Agenticle API server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
