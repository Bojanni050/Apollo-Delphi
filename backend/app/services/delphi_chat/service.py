"""Delphi, the chat agent of a werkmap.

Delphi is the round icon that also sits next to "Delphi Pulse": click it and a small,
draggable chat opens, floating above whatever screen is open. Her speciality is focus:

* she answers only about the documents of the active werkmap and about Apollo itself;
* a question about anything else is politely refused instead of answered — she does not
  hold conversations outside the werkmap;
* she does not just answer: she thinks along ("filosofeert") about what the documents say,
  about conflicts between them and about how those conflicts are best resolved.

The reply is built from the documents of the werkmap (a retrieval leg finds the fragments
that match the question, the document list with its groups gives the overview) plus a short
description of Apollo itself. Earlier turns of the conversation are context for what is
being asked, nothing more. Both sides of every exchange are stored (``delphi_chat_messages``)
so a conversation can be inspected later.

With the mock provider (offline, no language model) the reply is extractive: the best
matching sentences of the retrieved fragments, stitched into a short reflection. The scope
check is then a heuristic: terms found in the werkmap's documents, or a question about
Apollo or the werkmap itself.
"""

from __future__ import annotations

import datetime as dt
import re

from dataclasses import dataclass, field
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider
from app.core.logging import get_logger
from app.models import Document, Workspace
from app.models.delphi_chat import DelphiChatMessage
from app.services import workspace_repo
from app.services.search.service import SearchService, query_terms

log = get_logger(__name__)

OUT_OF_SCOPE_MARKER = "OUT_OF_SCOPE"

MAX_FRAGMENT_CHARS = 1200
MAX_TURNS = 6
MAX_OVERVIEW_DOCS = 60

OUT_OF_SCOPE_TEXT = (
    "Daar wil ik liever niets over zeggen. Ik praat alleen over de documenten in deze werkmap "
    "en over Apollo zelf — daar zit mijn hele wereld."
)
NO_DOCUMENTS_TEXT = (
    "Er staan nog geen documenten in deze werkmap. Importeer er eerst een paar, "
    "dan denk ik graag met je mee."
)
NO_MATCH_TEXT = (
    "Hier vind ik niets over in de documenten van deze werkmap. Als het over Apollo zelf gaat, "
    "help ik je graag; anders houdt mijn kennis hier echt op."
)

APOLLO_SELF = (
    "Apollo is een werkplek voor documenten. Je importeert documenten in een werkmap; Delphi Pulse "
    "stelt daarna thema's, groepen en verbanden voor die je aanneemt of wegwuift; Analyse leest claims "
    "uit de documenten en houdt ze tegen het licht; Delphi Weave toont hoe alles aan elkaar hangt. "
    "Vragen stelt Apollo ook: het antwoord citeert altijd de fragmenten waarop het berust. "
    "Delphi — ik — ben de chatagent die met je meedenkt over die documenten en hun conflicten."
)

SYSTEM_PROMPT = (
    "Je bent Delphi, de chatagent van Apollo. Je staat los van alle schermen: de gebruiker praat met "
    "je via een klein zwevend venster. Je specialisme is focus: je beantwoordt vragen ALLÉÉN over de "
    "documenten van de actieve werkmap en over Apollo zelf. Gesprekken daarbuiten voer je niet: antwoord "
    "dan met precies OUT_OF_SCOPE en niets anders. Je gebruikt alleen de meegegeven documentfragmenten "
    "en de informatie over Apollo; geen buitenkennis. Denk mee en filosofeer: wat de documenten zeggen, "
    "waar ze met elkaar in conflict raken en hoe die conflicten het beste op te lossen zijn — benoem "
    "documenten bij naam. Wees beknoop en menselijk, zonder opsmuk of citatiemarkeringen. "
    "Antwoord in de taal van de vraag."
)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_SELF_TERMS = {"apollo", "werkmap", "werkmaps", "pulse", "weave", "analyse", "importeren", "documenten", "document", "delphi", "app", "applicatie"}


@dataclass
class _Turn:
    role: str
    content: str


@dataclass
class ChatResult:
    reply: DelphiChatMessage
    user_message: DelphiChatMessage
    refusals: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _is_about_self(message: str) -> bool:
    """Whether a message is about Apollo or the werkmap itself (Dutch or English)."""
    words = {w.strip(".,'-:?!").lower() for w in re.findall(r"\w[\w'-]*", message)}
    return bool(words & _SELF_TERMS)


def _reflective_reply(question: str, excerpts: list[str]) -> str | None:
    """Offline reply: the best matching sentences of the fragments, as a short reflection."""
    terms = set(query_terms(question))
    best: list[tuple[int, str]] = []
    for excerpt in excerpts:
        for sentence in _sentences(excerpt):
            words = {w.strip(".,'-").lower() for w in re.findall(r"\w[\w.,'-]*\w|\w", sentence)}
            overlap = len(terms & words)
            if overlap > 1:
                best.append((overlap, sentence))
    if not best:
        return None
    best.sort(key=lambda p: -p[0])
    lines = [s for _, s in best[:3]]
    reflection = " ".join(lines)
    return (
        f"Dit is wat de documenten zeggen: {reflection} "
        "Ik vind het interessant om hier even bij stil te staan: als je ergens conflicten ziet "
        "tussen teksten, noem ze dan, dan denken we samen na over hoe die op te lossen zijn."
    )


def _overview_lines(db: Session, workspace_id: int) -> list[str]:
    rows = (
        db.query(Document.filename, Document.group_name)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.id)
        .limit(MAX_OVERVIEW_DOCS)
        .all()
    )
    return [f"- {name} (groep: {group or 'geen'})" for name, group in rows]


def _conversation_lines(turns: list[_Turn]) -> list[str]:
    return [f"{'Gebruiker' if t.role == 'user' else 'Delphi'}: {t.content}" for t in turns]


def _build_prompt(message: str, overview: list[str], fragments: list[str], turns: list[_Turn]) -> str:
    parts = ["Documenten in de werkmap:", *overview, "", "Fragmenten die bij de vraag passen:"]
    for i, fragment in enumerate(fragments, start=1):
        parts.append(f"[{i}] {fragment[:MAX_FRAGMENT_CHARS]}")
    parts += ["", f"Over Apollo zelf, als de vraag daarover gaat: {APOLLO_SELF}"]
    if turns:
        parts += ["", "Gesprek tot nu toe (context, geen bron):", *_conversation_lines(turns)]
    parts += ["", f"Vraag van de gebruiker: {message}"]
    return "\n".join(parts)


class DelphiChatService:
    def __init__(self, search: SearchService | None = None, llm: LLMProvider | None = None):
        self.search = search or SearchService()
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    def _turns(self, db: Session, parent: DelphiChatMessage | None) -> list[_Turn]:
        if parent is None:
            return []
        chain: list[DelphiChatMessage] = []
        seen: set[int] = set()
        node: DelphiChatMessage | None = parent
        while node is not None and node.id not in seen:
            seen.add(node.id)
            chain.append(node)
            node = db.get(DelphiChatMessage, node.parent_id) if node.parent_id else None
        chain.reverse()
        return [_Turn(role=m.role, content=m.content) for m in chain[-MAX_TURNS:]]

    async def chat(
        self, db: Session, message: str, workspace_id: int, parent: DelphiChatMessage | None = None
    ) -> ChatResult:
        message = message.strip()
        settings = get_settings()
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise LLMError("Werkmap niet gevonden")

        user_message = DelphiChatMessage(
            workspace_id=workspace_id, parent_id=parent.id if parent else None, role="user", content=message
        )
        db.add(user_message)
        db.flush()

        turns = self._turns(db, parent)
        overview = _overview_lines(db, workspace_id)
        doc_ids = [r[0] for r in db.query(Document.id).filter(Document.workspace_id == workspace_id)]

        fragments: list[str] = []
        if doc_ids:
            try:
                hits = await self.search.search(
                    db, message, top_k=min(settings.ask_top_k, 6), document_ids=doc_ids
                )
                fragments = [h.excerpt[:MAX_FRAGMENT_CHARS] for h in hits]
            except Exception:  # retrieval failing must not break the chat; Delphi still has the overview
                log.warning("delphi chat: retrieval failed, continuing with the document list only")

        content, refusal = await self._compose(message, overview, fragments, turns)

        reply = DelphiChatMessage(
            workspace_id=workspace_id,
            parent_id=user_message.id,
            role="delphi",
            content=content,
            refusal=refusal,
        )
        db.add(reply)
        db.commit()
        db.refresh(reply)
        db.refresh(user_message)
        self._log_to_repo(db, workspace, user_message, reply)
        return ChatResult(user_message=user_message, reply=reply)

    @staticmethod
    def _log_to_repo(db: Session, workspace: Workspace, user_message: DelphiChatMessage, reply: DelphiChatMessage) -> None:
        """Make the exchange part of the werkmap's git repository, the way human decisions are.
        Failing here must never cost a user their answer."""
        try:
            if workspace.working_dir is None:  # werkmap created before werkmappen were repositories
                workspace.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(workspace.id, workspace.name)))
                db.commit()
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            entries = [
                {
                    "at": now,
                    "workspace_id": workspace.id,
                    "exchange": user_message.id,
                    "role": "user",
                    "content": user_message.content,
                },
                {
                    "at": now,
                    "workspace_id": workspace.id,
                    "exchange": user_message.id,
                    "role": "delphi",
                    "content": reply.content,
                    "refusal": reply.refusal,
                },
            ]
            summary = user_message.content[:60] + ("..." if len(user_message.content) > 60 else "")
            workspace_repo.record_delphi_chat(
                Path(workspace.working_dir),
                entries,
                f"Delphi chat: {summary}",
            )
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not record the Delphi chat of werkmap %s in its repository: %s", workspace.id, exc)

    async def _compose(
        self, message: str, overview: list[str], fragments: list[str], turns: list[_Turn]
    ) -> tuple[str, str | None]:
        llm = self.llm
        if not overview:
            words = {w.strip(".,'-:?!").lower() for w in re.findall(r"\w[\w'-]*", message)}
            about_documents = bool(words & {"document", "documenten", "documenten", "docs"})
            if _is_about_self(message) and not about_documents:
                return APOLLO_SELF, None
            return NO_DOCUMENTS_TEXT, "no_documents"
        if llm.name == "mock":
            reply = _reflective_reply(message, fragments)
            if reply is not None:
                return reply, None
            if _is_about_self(message):
                return APOLLO_SELF, None
            return NO_MATCH_TEXT, "out_of_scope"
        raw = ((await llm.complete(SYSTEM_PROMPT, _build_prompt(message, overview, fragments, turns))) or "").strip()
        if raw.upper().startswith(OUT_OF_SCOPE_MARKER):
            return OUT_OF_SCOPE_TEXT, "out_of_scope"
        return raw or NO_MATCH_TEXT, None
