from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_key: Optional[str] = None
    channel: Optional[str] = "web"
    document_type: Optional[str] = None
    organism: Optional[str] = None
    topic: Optional[str] = None


class ChatSourceItem(BaseModel):
    document_id: int
    title: str
    url: Optional[str] = None
    document_type: Optional[str] = None
    similarity: Optional[float] = None
    snippet: Optional[str] = None
    content_kind: Optional[str] = None
    page_number: Optional[int] = None
    image_path: Optional[str] = None
    crop_path: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    session_key: str
    sources: list[ChatSourceItem] = []
    used_chunks: int = 0
    confidence: str = "medium"


class SourceCreate(BaseModel):
    name: str
    base_url: Optional[str] = None
    source_kind: str = "website"
    discovery_config_json: dict = {}


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    source_kind: Optional[str] = None
    is_active: Optional[bool] = None
    discovery_config_json: Optional[dict] = None


class DocumentPublishRequest(BaseModel):
    is_published: bool


class ManualDocumentCreate(BaseModel):
    title: str = Field(..., min_length=3)
    url: Optional[str] = None
    document_type: Optional[str] = None
    organism: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    content_text: str = Field(..., min_length=10)
    is_published: bool = True


class DocumentUpdateRequest(BaseModel):
    title: str = Field(..., min_length=3)
    url: Optional[str] = None
    document_type: Optional[str] = None
    organism: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    content_text: str = Field(..., min_length=10)
    is_published: bool = True


class RawIngestRequest(BaseModel):
    source_id: Optional[int] = None
    title: str = Field(..., min_length=3)
    url: Optional[str] = None
    document_type: Optional[str] = None
    organism: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    content_text: str = Field(..., min_length=10)
    is_published: bool = True


class DiscoveryItem(BaseModel):
    url: str
    title: Optional[str] = None
    kind: Optional[str] = None


class DiscoverySaveRequest(BaseModel):
    source_id: int
    items: list[DiscoveryItem] = []


class SourceRunIngestRequest(BaseModel):
    source_id: int


class CandidatePromoteRequest(BaseModel):
    document_type: Optional[str] = None
    organism: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    is_published: bool = True