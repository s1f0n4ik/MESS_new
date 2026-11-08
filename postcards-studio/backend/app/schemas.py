from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    email: str
    password: str


class UserView(BaseModel):
    id: int
    email: str
    name: str
    role: str


class SaveDocumentBody(BaseModel):
    baseRevision: int = 0
    pages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class RenameDocumentBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CreateUserBody(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=10)
    role: str = "editor"


class RestoreBody(BaseModel):
    baseRevision: int


class CollaborationAuthBody(BaseModel):
    token: str
    documentName: str


class CollaborationSnapshotBody(BaseModel):
    pages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    templateRevision: int | None = None
    updatedBy: str | None = None
    checkpoint: bool = False


class SaveTemplateBody(BaseModel):
    pages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    templateRevision: int | None = None


class TextFlowField(BaseModel):
    w: float = Field(gt=0, le=1, allow_inf_nan=False)
    h: float = Field(gt=0, le=1, allow_inf_nan=False)
    fontSize: float = Field(ge=6, le=240, allow_inf_nan=False)
    fontFamily: Literal['Times New Roman', 'Arial', 'Georgia', 'Courier New']
    bold: bool = False
    italic: bool = False


class TextFlowBody(BaseModel):
    page: int = Field(ge=1, le=200)
    itemId: str = Field(max_length=80)
    text: str = Field(max_length=60000)
    templateRevision: int
    fields: list[TextFlowField] | None = Field(default=None, min_length=2, max_length=2)


class MoveSpreadBody(BaseModel):
    fromSpread: int = Field(ge=1, le=100)
    toSpread: int = Field(ge=1, le=100)
    templateRevision: int


class AddSpreadBody(BaseModel):
    afterSpread: int = Field(ge=0, le=100)
    templateRevision: int
