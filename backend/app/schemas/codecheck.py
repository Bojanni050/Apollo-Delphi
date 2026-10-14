from __future__ import annotations

from pydantic import BaseModel, Field


class RepoRef(BaseModel):
    #: Al geïmporteerde repository (document_id van het github-document).
    document_id: int | None = None
    #: Nog niet geïmporteerde repository (wordt nu geïmporteerd in dezelfde werkmap).
    url: str | None = Field(default=None, min_length=3, max_length=512)


class CodecheckRequest(BaseModel):
    workspace_id: int | None = None
    #: De vastgelegde gegevens: geüploade documenten (hooguit 10, "een paar").
    document_ids: list[int] = Field(min_length=1, max_length=10)
    #: De code ernaast: hooguit 4 repo's (afgesproken maximum).
    repos: list[RepoRef] = Field(min_length=1, max_length=4)
