import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pathlib import Path
import asyncio
import json

from .agent import Agent
from .event import Event
from .group import Group

class Dashboard:
    """
    A real-time monitoring dashboard for Agenticle Agents and Groups.
    """
    def __init__(self, agent_or_group: Agent | Group, **kwargs):
        self.agent_or_group = agent_or_group
        self.app = FastAPI()
        self.kwargs = kwargs

        # Placeholder for the HTML content
        web_dir = Path(__file__).parent.resolve() / "web"
        self.html_path = web_dir / "index.html"

        @self.app.get("/")
        async def read_root():
            if not self.html_path.exists():
                return HTMLResponse("<html><body><h1>Error: index.html not found.</h1></body></html>", status_code=404)
            return HTMLResponse(self.html_path.read_text())

        @self.app.get("/events")
        async def stream_events():
            async def event_generator():
                event_stream = self.agent_or_group.run(stream=True, **self.kwargs)
                try:
                    for event in event_stream:
                        yield f"data: {json.dumps(event.__dict__)}\n\n"
                        await asyncio.sleep(0.1)  # Small delay to prevent overwhelming the client
                    # After the stream is finished, send a special event to the client
                    end_event = Event(source="Dashboard", type="session_end", payload={})
                    yield f"data: {json.dumps(end_event.__dict__)}\n\n"
                except asyncio.CancelledError:
                    print("Client disconnected.")

            return StreamingResponse(event_generator(), media_type="text/event-stream")

    def run(self, host: str = "127.0.0.1", port: int = 8000):
        """
        Run the dashboard server.
        """
        print(f"Starting Agenticle Dashboard at http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port)
