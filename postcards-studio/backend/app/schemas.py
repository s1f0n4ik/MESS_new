from typing import Any

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
    updatedBy: str | None = None
