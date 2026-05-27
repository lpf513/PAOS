from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter()


@router.websocket("/agent-events")
async def agent_events(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "connected", "message": "PAOS agent event stream ready"})

    try:
        while True:
            payload = await websocket.receive_json()
            await websocket.send_json({"type": "echo", "payload": payload})
    except WebSocketDisconnect:
        return
