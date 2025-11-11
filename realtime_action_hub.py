import json
from typing import List, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status

# ----------------------------------------------------------------------
# 1. Connection Manager (Handles WebSocket connections)
# ----------------------------------------------------------------------


class ConnectionManager:
    """
    Manages active WebSocket connections and handles broadcasting messages.
    """

    def __init__(self):
        # List of active WebSocket connections
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts and registers a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected: {websocket.client.host}")

    def disconnect(self, websocket: WebSocket):
        """Removes a disconnected WebSocket connection."""
        self.active_connections.remove(websocket)
        print(f"Client disconnected: {websocket.client.host}")

    async def broadcast(self, message: str):
        """Sends a message to all active clients."""
        # Use an error-safe broadcast loop
        disconnected_sockets = []
        for connection in self.active_connections:
            try:
                # Send the text message asynchronously
                await connection.send_text(message)
            except RuntimeError:
                # Handle cases where the connection might be closed right before sending
                disconnected_sockets.append(connection)
            except Exception as e:
                # Handle other exceptions (e.g., if the client disconnects unexpectedly)
                print(f"Error broadcasting to client: {e}")
                disconnected_sockets.append(connection)

        # Clean up disconnected sockets after iteration
        for socket in disconnected_sockets:
            if socket in self.active_connections:
                self.active_connections.remove(socket)

        print(
            f"Broadcasted: '{message}' to {len(self.active_connections)} active clients."
        )


# Initialize the connection manager
manager = ConnectionManager()
app = FastAPI(title="Real-Time Action Broadcast Hub (Single WS Channel)")


# ----------------------------------------------------------------------
# 3. HTTP Endpoint (Receives the Command)
# ----------------------------------------------------------------------


@app.post("/send_action", status_code=status.HTTP_200_OK)
async def send_action(
    action: Literal["pull", "push", "right", "left", "rotateForwards", "rotateReverse"],
):
    """
    Receives an action command via HTTP POST and broadcasts it to all connected WebSockets.
    """
    try:
        # Convert the Pydantic model to a JSON string for broadcasting
        # This ensures the clients receive structured data
        # broadcast_data = json.dumps({"action": action})
        if action == "left":
            broadcast_data = "right"
        elif action == "right":
            broadcast_data = "left"
        elif action == "rotateForwards":
            broadcast_data = "up"
        elif action == "rotateReverse":
            broadcast_data = "down"
        else:
            broadcast_data = action

        await manager.broadcast(broadcast_data)

        return {
            "status": "success",
            "message": f"Action '{action}' broadcasted to {len(manager.active_connections)} users.",
        }
    except Exception as e:
        # Log the error and return a 500 status
        print(f"Error during action broadcast: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast message: {e}",
        )


# ----------------------------------------------------------------------
# 4. WebSocket Endpoint (Connects Users to Receive Commands)
# ----------------------------------------------------------------------


@app.websocket("/ws")  # Changed to a single, generic endpoint
async def websocket_endpoint(websocket: WebSocket):
    """
    Handles individual WebSocket connections for clients on the single channel.
    """
    await manager.connect(websocket)

    # Broadcast a notification that a new client has joined
    await manager.broadcast(
        json.dumps(
            {
                "status": "connected",
                "message": "A new client joined the command channel.",
            }
        )
    )

    try:
        # Keep the connection open indefinitely. This loop keeps the socket alive.
        while True:
            # We must use 'await websocket.receive_text()' or similar to prevent the function from exiting.
            # If the client sends anything, we'll just acknowledge it here.
            data = await websocket.receive_text()
            print(f"Received message from client: {data}")

    except WebSocketDisconnect:
        # The client explicitly closed the connection or timed out
        manager.disconnect(websocket)
        # Broadcast the disconnection
        await manager.broadcast(
            json.dumps({"status": "disconnected", "message": "A client disconnected."})
        )
    except Exception as e:
        # Handle unexpected errors
        print(f"An unexpected error occurred for a client: {e}")
        manager.disconnect(websocket)
        await manager.broadcast(
            json.dumps(
                {"status": "error", "message": "A client disconnected due to error."}
            )
        )


# ----------------------------------------------------------------------
# 5. Root Endpoint (For simple health check)
# ----------------------------------------------------------------------


@app.get("/")
def read_root():
    return {"status": "ok", "service": "Real-Time Action Hub is running"}


# ----------------------------------------------------------------------
# How to Run:
# 1. Save this code as realtime_action_hub.py
# 2. Open your terminal in the same directory and run:
#    uvicorn realtime_action_hub:app --reload
#
# How to Test the WebSocket (Client 1):
# 1. Open your browser and navigate to: http://127.0.0.1:8000/docs
# 2. Go to the /ws endpoint and click 'Try it out'.
# 3. Click 'Connect'.
#
# How to Test the HTTP Broadcast (Injector):
# 1. Use another tab in the /docs page and navigate to the /send_action POST endpoint.
# 2. Click 'Try it out'.
# 3. Set the Request body to:
#    {
#      "action": "pull",
#      "source": "External_System_A"
#    }
# 4. Click 'Execute'.
#
# RESULT: You will see the message instantly appear in the WebSocket connection you established in step 4.
# ----------------------------------------------------------------------
