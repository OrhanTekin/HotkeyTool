"""
File-based note storage.

Layout under %APPDATA%/HotkeyTool/notes/:
    meta.json        – [{id, name}] in display order
    <uuid>.txt       – UTF-8 content for each note
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

_APPDATA  = Path(os.environ.get("APPDATA", Path.home()))
NOTES_DIR = _APPDATA / "HotkeyTool" / "notes"
_META     = NOTES_DIR / "meta.json"


@dataclass
class NoteFile:
    id: str
    name: str

    @property
    def path(self) -> Path:
        return NOTES_DIR / f"{self.id}.txt"


# ── meta helpers ──────────────────────────────────────────────────────────────

def _read_meta() -> List[NoteFile]:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not _META.exists():
        return []
    try:
        with open(_META, encoding="utf-8") as f:
            return [NoteFile(id=e["id"], name=e["name"]) for e in json.load(f)]
    except Exception:
        return []


def _write_meta(notes: List[NoteFile]) -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _META.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([{"id": n.id, "name": n.name} for n in notes],
                  f, indent=2, ensure_ascii=False)
    tmp.replace(_META)


# ── public API ────────────────────────────────────────────────────────────────

def load_all() -> List[NoteFile]:
    return _read_meta()


def load_content(note: NoteFile) -> str:
    try:
        return note.path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def save_content(note: NoteFile, content: str) -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    note.path.write_text(content, encoding="utf-8")


def create_note(name: str) -> NoteFile:
    notes = _read_meta()
    note  = NoteFile(id=str(uuid.uuid4()), name=name)
    save_content(note, "")
    notes.append(note)
    _write_meta(notes)
    return note


def rename_note(note_id: str, new_name: str) -> None:
    notes = _read_meta()
    for n in notes:
        if n.id == note_id:
            n.name = new_name
    _write_meta(notes)


def delete_note(note_id: str) -> None:
    notes = _read_meta()
    target = next((n for n in notes if n.id == note_id), None)
    if target:
        try:
            target.path.unlink(missing_ok=True)
        except Exception:
            pass
    _write_meta([n for n in notes if n.id != note_id])


def migrate_from_config(config_notes: list) -> None:
    """One-time import of notes that were stored in config.json."""
    existing = {n.id for n in _read_meta()}
    new: List[NoteFile] = []
    for raw in config_notes:
        nid = raw.get("id", "")
        if not nid or nid in existing:
            continue
        note = NoteFile(id=nid, name=raw.get("name", "Note"))
        save_content(note, raw.get("content", ""))
        new.append(note)
    if new:
        _write_meta(_read_meta() + new)
