"""
Auxilliary models.
"""
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


from mognet.model.result_state import ResultState


class Upload(BaseModel):
    upload_id: UUID
    file_name: str


class Document(BaseModel):
    upload_id: UUID
    file_name: str
    contents: str


class Job(BaseModel):
    job_id: UUID


class UploadResult(BaseModel):
    documents: List[Document]
    errors: List[str]


class UploadJobResult(Job):
    job_id: UUID
    job_status: ResultState

    result: Optional[UploadResult]
