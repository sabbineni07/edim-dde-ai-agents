"""Agent definitions, prompts, and skills — Postgres store with seed fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from shared.config.agent_content_meta import chain_usage, enrich_usage_fields
from shared.config.agent_content_seed import AGENT_DEFINITIONS, AGENT_PROMPTS, AGENT_SKILLS
from shared.config.loader import get_platform_settings
from shared.services.agent_content_history import (
    build_content_diff,
    find_version_row,
    list_versions,
    seed_keys_for_agent,
    seed_prompt_item,
    seed_skill_item,
    version_summary,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

ContentSource = Literal["database", "seed"]

_MEM_DEFINITIONS: Dict[str, Dict[str, Any]] = {}
_MEM_PROMPTS: Dict[str, List[Dict[str, Any]]] = {}
_MEM_SKILLS: Dict[str, List[Dict[str, Any]]] = {}
_MEM_INITIALIZED = False
_SEED_CHECKED = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    raw = os.environ.get("USE_POSTGRES")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes")
    return bool(getattr(get_platform_settings(), "use_postgres", False))


def _init_mem_from_seed() -> None:
    global _MEM_INITIALIZED
    if _MEM_INITIALIZED:
        return
    now = _utcnow().isoformat()
    for item in AGENT_DEFINITIONS:
        row = dict(item)
        row["created_at"] = now
        row["updated_at"] = now
        _MEM_DEFINITIONS[row["agent_id"]] = row
    for item in AGENT_PROMPTS:
        agent_id = item["agent_id"]
        prompt = {
            **item,
            "version": 1,
            "is_active": True,
            "updated_by": None,
            "created_at": now,
            "updated_at": now,
        }
        _MEM_PROMPTS.setdefault(agent_id, []).append(prompt)
    for item in AGENT_SKILLS:
        agent_id = item["agent_id"]
        skill = {
            **item,
            "version": 1,
            "is_active": True,
            "updated_by": None,
            "created_at": now,
            "updated_at": now,
        }
        _MEM_SKILLS.setdefault(agent_id, []).append(skill)
    for prompts in _MEM_PROMPTS.values():
        prompts.sort(
            key=lambda p: (p.get("sort_order", 0), p.get("chain_name", ""), p.get("role", ""))
        )
    for skills in _MEM_SKILLS.values():
        skills.sort(key=lambda s: (s.get("sort_order", 0), s.get("skill_key", "")))
    _MEM_INITIALIZED = True


def reset_agent_content_store_for_tests() -> None:
    """Clear in-memory store (unit tests only)."""
    global _MEM_DEFINITIONS, _MEM_PROMPTS, _MEM_SKILLS, _MEM_INITIALIZED, _SEED_CHECKED
    _MEM_DEFINITIONS = {}
    _MEM_PROMPTS = {}
    _MEM_SKILLS = {}
    _MEM_INITIALIZED = False
    _SEED_CHECKED = False


@dataclass(frozen=True)
class AgentContentBundle:
    agent_id: str
    definition: Dict[str, Any]
    prompts: List[Dict[str, Any]]
    skills: List[Dict[str, Any]]
    source: ContentSource
    chain_usage: Dict[str, Dict[str, Any]]

    def to_dict(self, *, can_edit: bool = False) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "definition": self.definition,
            "prompts": self.prompts,
            "skills": self.skills,
            "source": self.source,
            "chain_usage": self.chain_usage,
            "can_edit": can_edit,
        }


def _enrich_prompts(agent_id: str, prompts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        enrich_usage_fields(
            p,
            kind="prompt",
            agent_id=agent_id,
            chain_name=p.get("chain_name"),
            role=p.get("role"),
        )
        for p in prompts
    ]


def _enrich_skills(agent_id: str, skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        enrich_usage_fields(
            s,
            kind="skill",
            agent_id=agent_id,
            skill_key=s.get("skill_key"),
        )
        for s in skills
    ]


def _chain_usage_for_prompts(prompts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in prompts:
        name = str(p.get("chain_name") or "")
        if name and name not in out:
            meta = chain_usage(name)
            if meta:
                out[name] = dict(meta)
    return out


class AgentContentService:
    def seed_if_empty(self) -> int:
        """Insert seed rows when empty; also add any missing seeded agents."""
        global _SEED_CHECKED
        if not _db_enabled():
            _init_mem_from_seed()
            return len(_MEM_DEFINITIONS)

        if _SEED_CHECKED:
            return 0

        from shared.database.connection import get_database_session
        from shared.database.models import AgentDefinitionRow, AgentPromptRow, AgentSkillRow

        session = get_database_session()
        try:
            existing_ids = {r.agent_id for r in session.query(AgentDefinitionRow.agent_id).all()}
            now = _utcnow()
            inserted = 0
            for item in AGENT_DEFINITIONS:
                agent_id = item["agent_id"]
                if agent_id in existing_ids:
                    continue
                session.add(
                    AgentDefinitionRow(
                        agent_id=agent_id,
                        display_name=item["display_name"],
                        description=item.get("description"),
                        version=item.get("version", 1),
                        is_enabled=bool(item.get("is_enabled", True)),
                        get_started_route=item.get("get_started_route", "/app/environments"),
                        created_at=now,
                        updated_at=now,
                    )
                )
                for p in AGENT_PROMPTS:
                    if p["agent_id"] != agent_id:
                        continue
                    session.add(
                        AgentPromptRow(
                            agent_id=agent_id,
                            chain_name=p["chain_name"],
                            role=p["role"],
                            content=p["content"],
                            version=1,
                            is_active=True,
                            sort_order=int(p.get("sort_order", 0)),
                            updated_by=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                for s in AGENT_SKILLS:
                    if s["agent_id"] != agent_id:
                        continue
                    session.add(
                        AgentSkillRow(
                            agent_id=agent_id,
                            skill_key=s["skill_key"],
                            title=s["title"],
                            description=s.get("description"),
                            content=s["content"],
                            version=1,
                            is_active=True,
                            sort_order=int(s.get("sort_order", 0)),
                            updated_by=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                inserted += 1
            if inserted:
                session.commit()
                logger.info("agent_content_seeded", agents=inserted)
            _SEED_CHECKED = True
            return inserted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_content(self, agent_id: str) -> Optional[AgentContentBundle]:
        if not _db_enabled():
            _init_mem_from_seed()
            definition = _MEM_DEFINITIONS.get(agent_id)
            if not definition:
                return None
            prompts = _enrich_prompts(
                agent_id,
                [dict(p) for p in _MEM_PROMPTS.get(agent_id, []) if p.get("is_active", True)],
            )
            skills = _enrich_skills(
                agent_id,
                [dict(s) for s in _MEM_SKILLS.get(agent_id, []) if s.get("is_active", True)],
            )
            return AgentContentBundle(
                agent_id=agent_id,
                definition=dict(definition),
                prompts=prompts,
                skills=skills,
                source="seed",
                chain_usage=_chain_usage_for_prompts(prompts),
            )

        from shared.database.connection import get_database_session
        from shared.database.models import AgentDefinitionRow, AgentPromptRow, AgentSkillRow

        session = get_database_session()
        try:
            row = (
                session.query(AgentDefinitionRow)
                .filter(AgentDefinitionRow.agent_id == agent_id)
                .first()
            )
            if not row:
                return None
            definition = {
                "agent_id": row.agent_id,
                "display_name": row.display_name,
                "description": row.description,
                "version": row.version,
                "is_enabled": row.is_enabled,
                "get_started_route": row.get_started_route,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            prompt_rows = (
                session.query(AgentPromptRow)
                .filter(
                    AgentPromptRow.agent_id == agent_id,
                    AgentPromptRow.is_active.is_(True),
                )
                .order_by(AgentPromptRow.sort_order, AgentPromptRow.chain_name, AgentPromptRow.role)
                .all()
            )
            skill_rows = (
                session.query(AgentSkillRow)
                .filter(
                    AgentSkillRow.agent_id == agent_id,
                    AgentSkillRow.is_active.is_(True),
                )
                .order_by(AgentSkillRow.sort_order, AgentSkillRow.skill_key)
                .all()
            )
            prompts = _enrich_prompts(
                agent_id,
                [
                    {
                        "chain_name": p.chain_name,
                        "role": p.role,
                        "content": p.content,
                        "version": p.version,
                        "sort_order": p.sort_order,
                        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                        "updated_by": p.updated_by,
                    }
                    for p in prompt_rows
                ],
            )
            skills = _enrich_skills(
                agent_id,
                [
                    {
                        "skill_key": s.skill_key,
                        "title": s.title,
                        "description": s.description,
                        "content": s.content,
                        "version": s.version,
                        "sort_order": s.sort_order,
                        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                        "updated_by": s.updated_by,
                    }
                    for s in skill_rows
                ],
            )
            return AgentContentBundle(
                agent_id=agent_id,
                definition=definition,
                prompts=prompts,
                skills=skills,
                source="database",
                chain_usage=_chain_usage_for_prompts(prompts),
            )
        finally:
            session.close()

    def get_prompt_content(self, agent_id: str, chain_name: str, role: str) -> Optional[str]:
        if not _db_enabled():
            _init_mem_from_seed()
            for p in _MEM_PROMPTS.get(agent_id, []):
                if (
                    p.get("chain_name") == chain_name
                    and p.get("role") == role
                    and p.get("is_active", True)
                ):
                    return str(p.get("content") or "")
            return None

        from shared.database.connection import get_database_session
        from shared.database.models import AgentPromptRow

        session = get_database_session()
        try:
            row = (
                session.query(AgentPromptRow)
                .filter(
                    AgentPromptRow.agent_id == agent_id,
                    AgentPromptRow.chain_name == chain_name,
                    AgentPromptRow.role == role,
                    AgentPromptRow.is_active.is_(True),
                )
                .first()
            )
            return row.content if row else None
        finally:
            session.close()

    def update_prompt(
        self,
        agent_id: str,
        chain_name: str,
        role: str,
        content: str,
        *,
        updated_by: str,
    ) -> Dict[str, Any]:
        from shared.config.agent_prompt_validation import validate_prompt_template

        validate_prompt_template(agent_id, chain_name, role, content)
        now = _utcnow()

        if not _db_enabled():
            _init_mem_from_seed()
            prompts = _MEM_PROMPTS.setdefault(agent_id, [])
            active = None
            for p in prompts:
                if (
                    p.get("chain_name") == chain_name
                    and p.get("role") == role
                    and p.get("is_active", True)
                ):
                    active = p
                    break
            if not active:
                raise KeyError(f"Prompt not found: {chain_name}/{role}")
            active["is_active"] = False
            new_row = {
                **{
                    k: active[k]
                    for k in ("chain_name", "role", "sort_order", "agent_id")
                    if k in active
                },
                "content": content,
                "version": int(active.get("version") or 1) + 1,
                "is_active": True,
                "updated_by": updated_by,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            prompts.append(new_row)
            return dict(new_row)

        from shared.database.connection import get_database_session
        from shared.database.models import AgentPromptRow

        session = get_database_session()
        try:
            row = (
                session.query(AgentPromptRow)
                .filter(
                    AgentPromptRow.agent_id == agent_id,
                    AgentPromptRow.chain_name == chain_name,
                    AgentPromptRow.role == role,
                    AgentPromptRow.is_active.is_(True),
                )
                .first()
            )
            if not row:
                raise KeyError(f"Prompt not found: {chain_name}/{role}")
            row.is_active = False
            new_row = AgentPromptRow(
                agent_id=agent_id,
                chain_name=chain_name,
                role=role,
                content=content,
                version=int(row.version or 1) + 1,
                is_active=True,
                sort_order=row.sort_order,
                updated_by=updated_by,
                created_at=now,
                updated_at=now,
            )
            session.add(new_row)
            session.commit()
            session.refresh(new_row)
            return {
                "chain_name": new_row.chain_name,
                "role": new_row.role,
                "content": new_row.content,
                "version": new_row.version,
                "sort_order": new_row.sort_order,
                "updated_at": new_row.updated_at.isoformat() if new_row.updated_at else None,
                "updated_by": new_row.updated_by,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_prompt_versions(
        self, agent_id: str, chain_name: str, role: str
    ) -> List[Dict[str, Any]]:
        if not _db_enabled():
            _init_mem_from_seed()
            rows = [
                p
                for p in _MEM_PROMPTS.get(agent_id, [])
                if p.get("chain_name") == chain_name and p.get("role") == role
            ]
            return list_versions(rows, key_fn=lambda r: int(r.get("version") or 1))

        from shared.database.connection import get_database_session
        from shared.database.models import AgentPromptRow

        session = get_database_session()
        try:
            rows = (
                session.query(AgentPromptRow)
                .filter(
                    AgentPromptRow.agent_id == agent_id,
                    AgentPromptRow.chain_name == chain_name,
                    AgentPromptRow.role == role,
                )
                .order_by(AgentPromptRow.version.desc())
                .all()
            )
            return [
                version_summary(
                    {
                        "version": r.version,
                        "is_active": r.is_active,
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        "updated_by": r.updated_by,
                        "content": r.content,
                    }
                )
                for r in rows
            ]
        finally:
            session.close()

    def diff_prompt_versions(
        self,
        agent_id: str,
        chain_name: str,
        role: str,
        *,
        from_version: int,
        to_version: int,
    ) -> Dict[str, Any]:
        if from_version == to_version:
            raise ValueError("from_version and to_version must differ")
        if not _db_enabled():
            _init_mem_from_seed()
            rows = _MEM_PROMPTS.get(agent_id, [])
            from_row = find_version_row(
                rows,
                version=from_version,
                match_fn=lambda r: r.get("chain_name") == chain_name and r.get("role") == role,
            )
            to_row = find_version_row(
                rows,
                version=to_version,
                match_fn=lambda r: r.get("chain_name") == chain_name and r.get("role") == role,
            )
        else:
            from shared.database.connection import get_database_session
            from shared.database.models import AgentPromptRow

            session = get_database_session()
            try:
                from_row = (
                    session.query(AgentPromptRow)
                    .filter(
                        AgentPromptRow.agent_id == agent_id,
                        AgentPromptRow.chain_name == chain_name,
                        AgentPromptRow.role == role,
                        AgentPromptRow.version == from_version,
                    )
                    .first()
                )
                to_row = (
                    session.query(AgentPromptRow)
                    .filter(
                        AgentPromptRow.agent_id == agent_id,
                        AgentPromptRow.chain_name == chain_name,
                        AgentPromptRow.role == role,
                        AgentPromptRow.version == to_version,
                    )
                    .first()
                )
            finally:
                session.close()
            from_row = (
                {
                    "content": from_row.content,
                }
                if from_row
                else None
            )
            to_row = (
                {
                    "content": to_row.content,
                }
                if to_row
                else None
            )

        if not from_row or not to_row:
            raise KeyError(f"Version not found: {from_version} or {to_version}")
        label = f"{chain_name}/{role}"
        return build_content_diff(
            from_version=from_version,
            to_version=to_version,
            from_content=str(from_row.get("content") or ""),
            to_content=str(to_row.get("content") or ""),
            label_prefix=label,
        )

    def update_skill(
        self,
        agent_id: str,
        skill_key: str,
        *,
        content: str,
        updated_by: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        text = (content or "").strip()
        if not text:
            raise ValueError("Skill content cannot be empty")
        now = _utcnow()

        if not _db_enabled():
            _init_mem_from_seed()
            skills = _MEM_SKILLS.setdefault(agent_id, [])
            active = None
            for s in skills:
                if s.get("skill_key") == skill_key and s.get("is_active", True):
                    active = s
                    break
            if not active:
                raise KeyError(f"Skill not found: {skill_key}")
            active["is_active"] = False
            new_row = {
                **{
                    k: active[k]
                    for k in ("skill_key", "title", "description", "sort_order", "agent_id")
                    if k in active
                },
                "content": text,
                "version": int(active.get("version") or 1) + 1,
                "is_active": True,
                "updated_by": updated_by,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            if title is not None:
                new_row["title"] = title
            if description is not None:
                new_row["description"] = description
            skills.append(new_row)
            return dict(new_row)

        from shared.database.connection import get_database_session
        from shared.database.models import AgentSkillRow

        session = get_database_session()
        try:
            row = (
                session.query(AgentSkillRow)
                .filter(
                    AgentSkillRow.agent_id == agent_id,
                    AgentSkillRow.skill_key == skill_key,
                    AgentSkillRow.is_active.is_(True),
                )
                .first()
            )
            if not row:
                raise KeyError(f"Skill not found: {skill_key}")
            row.is_active = False
            new_row = AgentSkillRow(
                agent_id=agent_id,
                skill_key=skill_key,
                title=title if title is not None else row.title,
                description=description if description is not None else row.description,
                content=text,
                version=int(row.version or 1) + 1,
                is_active=True,
                sort_order=row.sort_order,
                updated_by=updated_by,
                created_at=now,
                updated_at=now,
            )
            session.add(new_row)
            session.commit()
            session.refresh(new_row)
            return {
                "skill_key": new_row.skill_key,
                "title": new_row.title,
                "description": new_row.description,
                "content": new_row.content,
                "version": new_row.version,
                "sort_order": new_row.sort_order,
                "updated_at": new_row.updated_at.isoformat() if new_row.updated_at else None,
                "updated_by": new_row.updated_by,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_skill_versions(self, agent_id: str, skill_key: str) -> List[Dict[str, Any]]:
        if not _db_enabled():
            _init_mem_from_seed()
            rows = [s for s in _MEM_SKILLS.get(agent_id, []) if s.get("skill_key") == skill_key]
            return list_versions(rows, key_fn=lambda r: int(r.get("version") or 1))

        from shared.database.connection import get_database_session
        from shared.database.models import AgentSkillRow

        session = get_database_session()
        try:
            rows = (
                session.query(AgentSkillRow)
                .filter(
                    AgentSkillRow.agent_id == agent_id,
                    AgentSkillRow.skill_key == skill_key,
                )
                .order_by(AgentSkillRow.version.desc())
                .all()
            )
            return [
                version_summary(
                    {
                        "version": r.version,
                        "is_active": r.is_active,
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        "updated_by": r.updated_by,
                        "content": r.content,
                    }
                )
                for r in rows
            ]
        finally:
            session.close()

    def diff_skill_versions(
        self,
        agent_id: str,
        skill_key: str,
        *,
        from_version: int,
        to_version: int,
    ) -> Dict[str, Any]:
        if from_version == to_version:
            raise ValueError("from_version and to_version must differ")
        if not _db_enabled():
            _init_mem_from_seed()
            rows = _MEM_SKILLS.get(agent_id, [])
            from_row = find_version_row(
                rows,
                version=from_version,
                match_fn=lambda r: r.get("skill_key") == skill_key,
            )
            to_row = find_version_row(
                rows,
                version=to_version,
                match_fn=lambda r: r.get("skill_key") == skill_key,
            )
        else:
            from shared.database.connection import get_database_session
            from shared.database.models import AgentSkillRow

            session = get_database_session()
            try:
                from_db = (
                    session.query(AgentSkillRow)
                    .filter(
                        AgentSkillRow.agent_id == agent_id,
                        AgentSkillRow.skill_key == skill_key,
                        AgentSkillRow.version == from_version,
                    )
                    .first()
                )
                to_db = (
                    session.query(AgentSkillRow)
                    .filter(
                        AgentSkillRow.agent_id == agent_id,
                        AgentSkillRow.skill_key == skill_key,
                        AgentSkillRow.version == to_version,
                    )
                    .first()
                )
            finally:
                session.close()
            from_row = {"content": from_db.content} if from_db else None
            to_row = {"content": to_db.content} if to_db else None

        if not from_row or not to_row:
            raise KeyError(f"Version not found: {from_version} or {to_version}")
        return build_content_diff(
            from_version=from_version,
            to_version=to_version,
            from_content=str(from_row.get("content") or ""),
            to_content=str(to_row.get("content") or ""),
            label_prefix=skill_key,
        )

    def reset_to_seed(self, agent_id: str, *, updated_by: str) -> Dict[str, Any]:
        """Restore prompts and skills to seed defaults (new version rows when changed)."""
        prompt_keys, skill_keys = seed_keys_for_agent(agent_id)
        if not prompt_keys and not skill_keys:
            raise KeyError(f"No seed content for agent: {agent_id}")

        prompts_reset = 0
        skills_reset = 0

        for chain_name, role in prompt_keys:
            seed = seed_prompt_item(agent_id, chain_name, role)
            if not seed:
                continue
            current = self.get_prompt_content(agent_id, chain_name, role)
            if current == seed["content"]:
                continue
            self.update_prompt(
                agent_id,
                chain_name,
                role,
                seed["content"],
                updated_by=updated_by,
            )
            prompts_reset += 1

        for skill_key in skill_keys:
            seed = seed_skill_item(agent_id, skill_key)
            if not seed:
                continue
            current = None
            if not _db_enabled():
                _init_mem_from_seed()
                for s in _MEM_SKILLS.get(agent_id, []):
                    if s.get("skill_key") == skill_key and s.get("is_active", True):
                        current = str(s.get("content") or "")
                        break
            else:
                from shared.database.connection import get_database_session
                from shared.database.models import AgentSkillRow

                session = get_database_session()
                try:
                    row = (
                        session.query(AgentSkillRow)
                        .filter(
                            AgentSkillRow.agent_id == agent_id,
                            AgentSkillRow.skill_key == skill_key,
                            AgentSkillRow.is_active.is_(True),
                        )
                        .first()
                    )
                    current = row.content if row else None
                finally:
                    session.close()

            if current == seed["content"]:
                continue
            self.update_skill(
                agent_id,
                skill_key,
                content=seed["content"],
                updated_by=updated_by,
                title=seed.get("title"),
                description=seed.get("description"),
            )
            skills_reset += 1

        bundle = self.get_content(agent_id)
        if not bundle:
            raise KeyError(f"Agent content not found: {agent_id}")
        return {
            "agent_id": agent_id,
            "prompts_reset": prompts_reset,
            "skills_reset": skills_reset,
            "content": bundle.to_dict(can_edit=True),
        }


_svc = AgentContentService()


def seed_agent_content_if_empty() -> int:
    return _svc.seed_if_empty()


def get_agent_content(agent_id: str) -> Optional[AgentContentBundle]:
    return _svc.get_content(agent_id)


def get_prompt_content(agent_id: str, chain_name: str, role: str) -> Optional[str]:
    return _svc.get_prompt_content(agent_id, chain_name, role)


def update_agent_prompt(
    agent_id: str,
    chain_name: str,
    role: str,
    content: str,
    *,
    updated_by: str,
) -> Dict[str, Any]:
    return _svc.update_prompt(agent_id, chain_name, role, content, updated_by=updated_by)


def update_agent_skill(
    agent_id: str,
    skill_key: str,
    *,
    content: str,
    updated_by: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    return _svc.update_skill(
        agent_id,
        skill_key,
        content=content,
        updated_by=updated_by,
        title=title,
        description=description,
    )


def list_agent_prompt_versions(agent_id: str, chain_name: str, role: str) -> List[Dict[str, Any]]:
    return _svc.list_prompt_versions(agent_id, chain_name, role)


def list_agent_skill_versions(agent_id: str, skill_key: str) -> List[Dict[str, Any]]:
    return _svc.list_skill_versions(agent_id, skill_key)


def diff_agent_prompt_versions(
    agent_id: str,
    chain_name: str,
    role: str,
    *,
    from_version: int,
    to_version: int,
) -> Dict[str, Any]:
    return _svc.diff_prompt_versions(
        agent_id,
        chain_name,
        role,
        from_version=from_version,
        to_version=to_version,
    )


def diff_agent_skill_versions(
    agent_id: str,
    skill_key: str,
    *,
    from_version: int,
    to_version: int,
) -> Dict[str, Any]:
    return _svc.diff_skill_versions(
        agent_id,
        skill_key,
        from_version=from_version,
        to_version=to_version,
    )


def reset_agent_content_to_seed(agent_id: str, *, updated_by: str) -> Dict[str, Any]:
    return _svc.reset_to_seed(agent_id, updated_by=updated_by)
