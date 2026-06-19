from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Postcards Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {
    "roles": {"pc1": {}, "pc2": {}, "pc3": {}, "pc4": {}},
    "scenario": {"active": False, "waveIndex": 0, "waveSettled": False},
    "clicksByRole": {"pc1": 0, "pc2": 0, "pc3": 0, "pc4": 0},
}

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/state")
def get_state():
    return STATE

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "state", "payload": STATE})
    try:
        while True:
            data = await ws.receive_json()
            await ws.send_json({"type": "echo", "payload": data})
    except Exception:
        pass