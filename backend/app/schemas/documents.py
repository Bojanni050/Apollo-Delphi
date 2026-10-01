from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int | None
    filename: str
    source_type: str = "upload"
    source_url: str | None = None
    repo_path: str | None = None
    title: str | None
    file_type: str
    file_size: int
    #: SHA-256 of the file: lets a client see that it is already there before uploading it again.
    content_hash: str = ""
    indexing_status: str
    error_message: str | None
    created_at: dt.datetime
    indexed_at: dt.datetime | None
    document_date: dt.date | None


class FolderScanRequest(BaseModel):
    #: Full path of a folder on the machine the backend runs on.
    path: str


class FolderScanFileOut(BaseModel):
    path: str
    size: int
    content_hash: str


class FolderSkippedOut(BaseModel):
    path: str
    reason: str


class FolderScanOut(BaseModel):
    root: str
    #: The folder's own name: the first part of every imported file's name ("name/docs/a.md").
    name: str
    files: list[FolderScanFileOut]
    skipped: list[FolderSkippedOut]
    #: True when the folder holds more importable files than are listed.
    truncated: bool = False


class FolderFileRequest(BaseModel):
    root: str
    #: Path of the file below ``root``, as listed by the scan.
    path: str
    workspace_id: int | None = None


class IndexQueueRequest(BaseModel):
    #: Which documents to index. Omitted = every ``pending`` document of ``workspace_id``.
    document_ids: list[int] | None = None
    workspace_id: int | None = None


class IndexErrorOut(BaseModel):
    document_id: int
    filename: str
    error: str | None = None


class IndexQueueOut(BaseModel):
    """Progress of the background indexing batch."""

    active: bool
    #: Documents queued in this batch, how many are read (parsed), how many are completely indexed, how many failed.
    total: int
    parsed: int
    done: int
    failed: int
    #: "lezen" or "embedden" while a document is being worked on, with its name.
    phase: str | None = None
    current: str | None = None
    #: Seconds of embedding per document so far in this batch; None before the first one is done.
    seconds_per_document: float | None = None
    errors: list[IndexErrorOut] = []
    #: How many documents this request added to the queue.
    added: int = 0


class ReadingChunkOut(BaseModel):
    id: int
    chunk_index: int
    section: str | None = None
    page_number: int | None = None
    #: Inclusive, 1-based lines in ``text``; None for a fragment indexed before line ranges existed.
    line_start: int | None = None
    line_end: int | None = None


class ReadingPageOut(BaseModel):
    page_number: int
    #: The line of ``text`` where the page starts.
    line: int


class DocumentHtmlOut(BaseModel):
    """A Word document converted to HTML for the reading pane (the browser sanitizes it before showing)."""

    html: str
    warnings: int = 0


class DocumentTextOut(BaseModel):
    """What the reading pane shows: the extracted text of a document, its pages and where its indexed fragments lie."""

    id: int
    workspace_id: int | None
    filename: str
    title: str | None
    file_type: str
    source_type: str
    text: str
    line_count: int
    pages: list[ReadingPageOut]
    chunks: list[ReadingChunkOut]
    #: The text was cut at a limit.
    truncated: bool = False
