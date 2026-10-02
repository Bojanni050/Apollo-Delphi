"""A note made from a conversation with Delphi.

Asking Delphi "make a note of this" turns an exchange into a document: the model summarises the
conversation into a short, tidy note (with the mock provider the conversation text itself becomes the
note), which is stored as a ``GeneratedDocument`` of kind ``note`` — visible on the Generated page —
and written into the werkmap's git repository as ``Notes/Delphi/<slug>.md``, so it is a real file
among the other documents, with its own commit.

The note records where it came from (the exchange it summarises) in its metadata; the chat itself
stays in ``Conversations/delphi-chat.jsonl`` untouched.
"""

from __future__ import annotations

import datetime as dt
import re

from pathlib import Path
from sqlalchemy.orm import Session

from app.core.llm import LLMProvider, get_llm_provider
from app.core.logging import get_logger
from app.models import Workspace
from app.models.delphi_chat import DelphiChatMessage
from app.models.generated_document import GeneratedDocument
from app.services import workspace_repo

log = get_logger(__name__)

MAX_NOTE_CHARS = 6000
_SLUG_RE = re.compile(r"[^a-z0-9]+")

NOTE_SYSTEM_PROMPT = (
    "You turn a conversation with Delphi, the chat agent of a document workspace, into a short note "
    "the user can keep. Use ONLY what the conversation says; never add outside knowledge or opinions. "
    "Write in the language of the conversation, in Markdown: a '# ' title line, then a few compact "
    "paragraphs or bullets that capture what was discussed and concluded. Keep it short and factual. "
    "Reply with the note only, no preamble."
)


def _slug(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")[:60]
    return slug or "notitie"


class DelphiNoteService:
    def __init__(self, llm: LLMProvider | None = None):
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    async def make_note(self, db: Session, workspace_id: int, reply_id: int) -> GeneratedDocument:
        """Turn the exchange that ``reply_id`` belongs to into a note. Raises ValueError when the
        reply does not exist or belongs to another werkmap."""
        reply = db.get(DelphiChatMessage, reply_id)
        if reply is None or reply.workspace_id != workspace_id:
            raise ValueError("That reply is not part of this werkmap")
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Werkmap niet gevonden")

        # the exchange: the user message this reply answers, the reply itself, and the turns around it
        user_message = db.get(DelphiChatMessage, reply.parent_id) if reply.parent_id else None
        turns = self._exchange(db, reply)
        conversation = "\n".join(
            f"{'Gebruiker' if m.role == 'user' else 'Delphi'}: {m.content}" for m in turns
        )[:MAX_NOTE_CHARS]

        content = await self._compose(conversation, reply)
        title = self._title(reply, user_message.content if user_message else "Notitie")

        doc = GeneratedDocument(
            workspace_id=workspace_id,
            title=title,
            status="drafted",
            doc_kind="note",
            content=content,
            verification_status="pending",
            revision=0,
            generation_metadata='{"source": "delphi_chat", "reply_id": %d}' % reply.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        self._store_in_repo(workspace, doc)
        return doc

    def _exchange(self, db: Session, reply: DelphiChatMessage) -> list[DelphiChatMessage]:
        """The chain the reply belongs to, up to and including the reply (its own conversation, not
        the ones that follow it)."""
        chain: list[DelphiChatMessage] = []
        seen: set[int] = set()
        node: DelphiChatMessage | None = reply
        while node is not None and node.id not in seen:
            seen.add(node.id)
            chain.append(node)
            node = db.get(DelphiChatMessage, node.parent_id) if node.parent_id else None
        chain.reverse()
        return chain

    async def _compose(self, conversation: str, reply: DelphiChatMessage) -> str:
        if self.llm.name == "mock":
            return f"# Notitie\n\n{conversation}"
        try:
            raw = (await self.llm.complete(NOTE_SYSTEM_PROMPT, conversation) or "").strip()
        except Exception as exc:  # a failing model must not cost the user their note
            log.warning("Delphi note: the model failed (%s); the conversation text becomes the note", exc)
            raw = ""
        if not raw:
            return f"# Notitie\n\n{conversation}"
        return raw

    def _title(self, reply: DelphiChatMessage, question: str) -> str:
        base = question.strip() or reply.content.strip() or "Notitie"
        title = " ".join(base.split())
        return (title[:80] + "…") if len(title) > 80 else title

    def _store_in_repo(self, workspace: Workspace, doc: GeneratedDocument) -> None:
        """Write the note into the werkmap as ``Notes/Delphi/<slug>.md``, its own commit. Failing
        here must not cost the user their note (it is already in the database)."""
        try:
            if workspace.working_dir is None:
                workspace.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(workspace.id, workspace.name)))
            notes = Path(workspace.working_dir) / "Notes" / "Delphi"
            notes.mkdir(parents=True, exist_ok=True)
            path = notes / f"{_slug(doc.title)}.md"
            n = 1
            stem = _slug(doc.title)
            while path.exists():
                n += 1
                path = notes / f"{stem}-{n}.md"
            body = doc.content or ""
            header = f"---\ntitle: {doc.title}\nmade_from: delphi chat ({dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})\n---\n\n"
            path.write_text(header + body, encoding="utf-8")
            rel = path.relative_to(workspace.working_dir).as_posix()
            from app.services.workspace_repo import _commit_paths

            _commit_paths(Path(workspace.working_dir), [rel], f"Add note from Delphi chat: {doc.title[:60]}")
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not store the Delphi note of werkmap %s in its repository: %s", workspace.id, exc)
