from pathlib import Path
from typing import Literal, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROLES = ["pc1", "pc2", "pc3", "pc4"]

app = FastAPI(title="Postcards Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_DIR = Path(__file__).parent / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")


def empty_flips():
    return {str(i): False for i in range(8)}


STATE = {
    "stateVersion": 1,
    "clicksByRole": {r: 0 for r in ROLES},
    "flippedCardsByRole": {r: empty_flips() for r in ROLES},
    "pdfsByRole": {
        "pc1": "pc1.pdf",
        "pc2": "pc2.pdf",
        "pc3": "pc3.pdf",
        "pc4": "pc4.pdf",
    },
    "pdfWindow": {
        "visible": False,
        "role": "pc1",
        "pdfFile": "pc1.pdf",
        "token": "",
    },
}


def bump():
    STATE["stateVersion"] += 1


class Action(BaseModel):
    type: Literal["card_click", "reset_clicks", "open_pdf", "close_pdf", "set_pdf_for_role"]
    role: Optional[str] = None
    cardIndex: Optional[int] = None
    pdfFile: Optional[str] = None
    targetRole: Optional[str] = None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/state")
def get_state():
    return STATE


@app.get("/api/pdfs")
def get_pdfs():
    files = sorted([p.name for p in PDF_DIR.glob("*.pdf")])
    return {"files": files}


@app.post("/api/action")
def apply_action(action: Action):
    role = action.role if action.role in ROLES else "pc1"

    if action.type == "card_click":
        idx = max(0, min(7, int(action.cardIndex or 0)))
        key = str(idx)
        STATE["clicksByRole"][role] += 1
        STATE["flippedCardsByRole"][role][key] = not STATE["flippedCardsByRole"][role][key]
        bump()
        return {"ok": True, "stateVersion": STATE["stateVersion"]}

    if action.type == "reset_clicks":
        STATE["clicksByRole"][role] = 0
        STATE["flippedCardsByRole"][role] = empty_flips()
        bump()
        return {"ok": True, "stateVersion": STATE["stateVersion"]}

    if action.type == "open_pdf":
        pdf = action.pdfFile or STATE["pdfsByRole"][role]
        STATE["pdfWindow"] = {
            "visible": True,
            "role": role,
            "pdfFile": pdf,
            "token": f"{STATE['stateVersion']+1}:{role}:{pdf}",
        }
        bump()
        return {"ok": True, "stateVersion": STATE["stateVersion"]}

    if action.type == "close_pdf":
        STATE["pdfWindow"]["visible"] = False
        STATE["pdfWindow"]["token"] = f"{STATE['stateVersion']+1}:close"
        bump()
        return {"ok": True, "stateVersion": STATE["stateVersion"]}

    if action.type == "set_pdf_for_role":
        tr = action.targetRole if action.targetRole in ROLES else role
        if action.pdfFile:
            STATE["pdfsByRole"][tr] = action.pdfFile
            bump()
        return {"ok": True, "stateVersion": STATE["stateVersion"]}

    return {"ok": False}