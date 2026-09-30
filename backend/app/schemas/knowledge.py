from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class KnowledgeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_run_id: int
    item_type: str
    statement: str
    explanation: str | None
    confidence: float
    provenance: str | None
    source_refs: str | None
    created_at: dt.datetime
