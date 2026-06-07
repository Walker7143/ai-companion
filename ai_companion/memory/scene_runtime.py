from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .scene_authority import categorize_scene_text, is_scene_authority_predicate, non_copresent_scene_reason


_SCENE_DURABILITY_BY_CATEGORY: dict[str, str] = {
    "bathroom": "momentary",
    "meal": "social",
    "vehicle": "travel",
    "outing": "travel",
    "intimate_room": "social",
    "sleep": "rest",
    "room_reset": "momentary",
}

_SCENE_FRESHNESS_MINUTES_BY_DURABILITY: dict[str, int] = {
    "momentary": 12,
    "social": 30,
    "travel": 75,
    "rest": 120,
    "ambient": 45,
}


def _parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _item_value(item: Any, key: str) -> Any:
    if hasattr(item, key):
        return getattr(item, key)
    if isinstance(item, dict):
        return item.get(key)
    return None


def _normalized_subject(value: object) -> str:
    subject = str(value or "").strip()
    if not subject:
        return "shared"
    return subject


def _scene_metadata(item: Any) -> dict[str, Any]:
    raw = _item_value(item, "metadata")
    return dict(raw) if isinstance(raw, dict) else {}


def _scene_categories_from_item(item: Any) -> set[str]:
    metadata = _scene_metadata(item)
    categories = metadata.get("scene_categories")
    if isinstance(categories, list):
        values = {str(value).strip() for value in categories if str(value).strip()}
        if values:
            return values
    if isinstance(categories, str) and categories.strip():
        return {categories.strip()}

    collected: set[str] = set()
    for key in ("value",):
        collected |= categorize_scene_text(_item_value(item, key))
    return collected


def _scene_names_from_item(item: Any) -> set[str]:
    metadata = _scene_metadata(item)
    scene_name = str(metadata.get("scene_name") or "").strip()
    if scene_name:
        return {scene_name}
    return _scene_categories_from_item(item)


def _scene_durability_for_names(scene_names: set[str], categories: set[str]) -> str:
    names = scene_names or categories
    durations = {
        _SCENE_DURABILITY_BY_CATEGORY.get(name, "ambient")
        for name in names
    }
    if not durations:
        return "ambient"
    priority = ("momentary", "social", "travel", "rest", "ambient")
    for name in priority:
        if name in durations:
            return name
    return "ambient"


def _scene_freshness_minutes(items: list[Any], scene_names: set[str], categories: set[str]) -> int:
    explicit: list[int] = []
    for item in items:
        metadata = _scene_metadata(item)
        for key in ("scene_freshness_minutes", "freshness_minutes"):
            raw = metadata.get(key)
            try:
                if raw is not None:
                    explicit.append(max(1, int(raw)))
            except (TypeError, ValueError):
                continue
    if explicit:
        return min(explicit)
    durability = _scene_durability_for_names(scene_names, categories)
    return _SCENE_FRESHNESS_MINUTES_BY_DURABILITY.get(durability, 45)


@dataclass
class SceneSnapshot:
    scope_mode: str = "none"
    subject: str = ""
    location: str = ""
    activity: str = ""
    spatial: str = ""
    categories: set[str] = field(default_factory=set)
    scene_names: set[str] = field(default_factory=set)
    source_kinds: set[str] = field(default_factory=set)
    durability_class: str = "none"
    freshness_minutes: int = 0
    latest_update: datetime | None = None
    expires_at: datetime | None = None
    grounded_by_user: bool = False
    invalidated_by_user_context: bool = False
    evaluated_at: datetime = field(default_factory=datetime.now)

    @property
    def present(self) -> bool:
        return bool(self.location or self.activity or self.spatial)

    @property
    def is_shared_copresent(self) -> bool:
        return self.scope_mode == "shared_copresent" and self.present

    @property
    def is_fresh(self) -> bool:
        if not self.present:
            return False
        if self.expires_at and self.evaluated_at > self.expires_at:
            return False
        if self.latest_update is None:
            return True
        return self.evaluated_at - self.latest_update <= timedelta(minutes=max(1, self.freshness_minutes))

    @property
    def allows_copresent_actions(self) -> bool:
        return (
            self.is_shared_copresent
            and self.grounded_by_user
            and self.is_fresh
            and not self.invalidated_by_user_context
        )

    @property
    def should_anchor_generation(self) -> bool:
        return self.allows_copresent_actions

    def summary_text(self) -> str:
        parts: list[str] = []
        if self.location:
            parts.append(f"location={self.location}")
        if self.activity:
            parts.append(f"activity={self.activity}")
        if self.spatial:
            parts.append(f"spatial={self.spatial}")
        return "; ".join(parts)

    def to_live_context(self) -> dict[str, Any]:
        if not self.should_anchor_generation:
            return {
                "categories": [],
                "summary": "",
                "scope_mode": self.scope_mode,
                "grounded": False,
            }
        return {
            "categories": sorted(self.categories),
            "summary": self.summary_text()[:800],
            "scope_mode": self.scope_mode,
            "grounded": True,
        }


def build_scene_snapshot(
    active_states: list[Any],
    *,
    user_input: str = "",
    now: datetime | None = None,
) -> SceneSnapshot:
    evaluated_at = now or datetime.now()
    invalidated_by_user_context = bool(non_copresent_scene_reason(user_input))
    scene_items = [
        item
        for item in (active_states or [])
        if str(_item_value(item, "scope") or "").startswith("current_scene")
        and is_scene_authority_predicate(
            str(_item_value(item, "scope") or "").strip(),
            str(_item_value(item, "predicate") or "").strip(),
        )
    ]
    if not scene_items:
        return SceneSnapshot(
            invalidated_by_user_context=invalidated_by_user_context,
            evaluated_at=evaluated_at,
        )

    def _sort_key(item: Any) -> tuple[str, str]:
        return (
            str(_item_value(item, "updated_at") or _item_value(item, "effective_at") or ""),
            str(_item_value(item, "predicate") or ""),
        )

    ordered = sorted(scene_items, key=_sort_key)
    subject = _normalized_subject(_item_value(ordered[-1], "subject"))
    scope_mode = {
        "shared": "shared_copresent",
        "user": "user_only",
        "assistant": "assistant_only",
    }.get(subject, "user_only")
    selected = [item for item in ordered if _normalized_subject(_item_value(item, "subject")) == subject]
    if not selected:
        selected = ordered

    latest_by_predicate: dict[str, Any] = {}
    for item in selected:
        latest_by_predicate[str(_item_value(item, "predicate") or "").strip()] = item

    location = str(_item_value(latest_by_predicate.get("current_location"), "value") or _item_value(latest_by_predicate.get("location"), "value") or "").strip()
    activity = str(_item_value(latest_by_predicate.get("current_activity"), "value") or _item_value(latest_by_predicate.get("activity_type"), "value") or "").strip()
    spatial = str(_item_value(latest_by_predicate.get("spatial_relationship"), "value") or "").strip()

    categories: set[str] = set()
    scene_names: set[str] = set()
    source_kinds: set[str] = set()
    grounded_by_user = False
    latest_update: datetime | None = None
    expires_at: datetime | None = None
    for item in selected:
        categories |= _scene_categories_from_item(item)
        scene_names |= _scene_names_from_item(item)
        source_kind = str(_item_value(item, "source_kind") or "").strip()
        if source_kind:
            source_kinds.add(source_kind)
        metadata = _scene_metadata(item)
        if metadata.get("grounded_by_user") is True or source_kind in {"user_explicit", "joint_inference"}:
            grounded_by_user = True
        updated = _parse_iso_datetime(_item_value(item, "updated_at") or _item_value(item, "effective_at"))
        if updated and (latest_update is None or updated > latest_update):
            latest_update = updated
        item_expires = _parse_iso_datetime(_item_value(item, "expires_at"))
        if item_expires is not None and (expires_at is None or item_expires < expires_at):
            expires_at = item_expires

    durability = _scene_durability_for_names(scene_names, categories)
    freshness_minutes = _scene_freshness_minutes(selected, scene_names, categories)
    return SceneSnapshot(
        scope_mode=scope_mode,
        subject=subject,
        location=location,
        activity=activity,
        spatial=spatial,
        categories=categories,
        scene_names=scene_names,
        source_kinds=source_kinds,
        durability_class=durability,
        freshness_minutes=freshness_minutes,
        latest_update=latest_update,
        expires_at=expires_at,
        grounded_by_user=grounded_by_user,
        invalidated_by_user_context=invalidated_by_user_context,
        evaluated_at=evaluated_at,
    )
