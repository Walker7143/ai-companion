from __future__ import annotations

import re
from dataclasses import dataclass


_INSPECT_VERBS = (
    "\u68c0\u67e5",
    "\u6838\u5bf9",
    "\u5de1\u89c6",
    "\u9a8c\u6536",
    "\u67e5\u770b",
    "\u770b\u770b",
    "\u67e5",
    "\u76ef",
)
_CARETAKE_VERBS = (
    "\u7167\u770b",
    "\u7167\u5e94",
    "\u6253\u7406",
    "\u5904\u7406",
    "\u6536\u62fe",
    "\u6574\u7406",
    "\u5e2e\u5fd9\u770b",
)
_ALL_ACTION_VERBS = (*_INSPECT_VERBS, *_CARETAKE_VERBS)
_BUSINESS_ASSETS = (
    "\u5ba2\u6808",
    "\u6c11\u5bbf",
    "\u5e97",
    "\u95e8\u5e97",
    "\u516c\u53f8",
    "\u9879\u76ee",
    "\u5de5\u4f5c\u5ba4",
    "\u644a\u4f4d",
    "\u8d26",
    "\u8d26\u76ee",
)
_BUSINESS_ASSET_RE = "|".join(sorted((re.escape(item) for item in _BUSINESS_ASSETS), key=len, reverse=True))
_ASSISTANT_BUSINESS_ASSET_RE = re.compile(rf"\u4f60(?:\u7684)?(?P<asset>{_BUSINESS_ASSET_RE})")
_USER_BUSINESS_ASSET_RE = re.compile(rf"\u6211(?:\u7684)?(?P<asset>{_BUSINESS_ASSET_RE})")

_AUTHORITY_PATTERNS = (
    re.compile(r"\u6263\u4f60\u5de5\u8d44"),
    re.compile(r"\u7ed9\u4f60\u53d1\u5de5\u8d44"),
    re.compile(r"\u7ed9\u4f60\u5f00\u5de5\u8d44"),
    re.compile(r"\u6263\u4f60\u7ee9\u6548"),
    re.compile(r"\u7ed9\u4f60\u6392\u73ed"),
    re.compile(r"\u7ed9\u4f60\u6279\u5047"),
    re.compile(r"\u6279\u4f60\u5047"),
    re.compile(r"\u8bb0\u4f60\u65f7\u5de5"),
    re.compile(r"\u5f00\u9664\u4f60"),
    re.compile(r"\u8f9e\u9000\u4f60"),
    re.compile(r"\u8003\u6838\u4f60"),
)

_AUTHORITY_GRANT_PATTERNS = (
    re.compile(r"\u4f60\u662f\u6211\u8001\u677f"),
    re.compile(r"\u5f52\u4f60\u7ba1"),
    re.compile(r"\u542c\u4f60\u5b89\u6392"),
    re.compile(r"\u4f60\u7ed9\u6211\u53d1\u5de5\u8d44"),
    re.compile(r"\u4f60\u7ed9\u6211\u6392\u73ed"),
    re.compile(r"\u4f60\u7ed9\u6211\u6279\u5047"),
    re.compile(r"\u4f60\u662f\u5e97\u957f"),
    re.compile(r"\u4f60\u662f\u7ecf\u7406"),
)


@dataclass(frozen=True)
class TurnRoleSignal:
    actor: str
    owner: str
    action_family: str
    asset: str
    raw_action: str


def _normalize_action_family(action: str) -> str:
    value = str(action or "").strip()
    if value in _INSPECT_VERBS:
        return "inspect"
    if value in _CARETAKE_VERBS:
        return "caretake"
    return "other"


def _find_first_ordered_term(
    text: str,
    terms: tuple[str, ...],
    *,
    start: int = 0,
    limit: int = 36,
) -> tuple[int, str] | None:
    best: tuple[int, str] | None = None
    upper = min(len(text), start + max(0, limit))
    for term in terms:
        idx = text.find(term, start, upper)
        if idx < 0:
            continue
        if best is None or idx < best[0] or (idx == best[0] and len(term) > len(best[1])):
            best = (idx, term)
    return best


def _infer_actor_owner_signal(
    text: str,
    *,
    actor_token: str,
    owner_token: str,
    actor: str,
    owner: str,
) -> TurnRoleSignal | None:
    actor_idx = text.find(actor_token)
    if actor_idx < 0:
        return None
    action_match = _find_first_ordered_term(text, _ALL_ACTION_VERBS, start=actor_idx + len(actor_token), limit=24)
    if action_match is None:
        return None
    action_idx, action = action_match
    owner_idx = text.find(owner_token, action_idx + len(action), min(len(text), action_idx + len(action) + 24))
    if owner_idx < 0:
        return None
    asset_match = _find_first_ordered_term(text, _BUSINESS_ASSETS, start=owner_idx + len(owner_token), limit=10)
    if asset_match is None:
        return None
    _, asset = asset_match
    return TurnRoleSignal(
        actor=actor,
        owner=owner,
        action_family=_normalize_action_family(action),
        asset=asset,
        raw_action=action,
    )


def _find_actor_action_asset(text: str, *, actor_token: str) -> tuple[str, str] | None:
    actor_idx = text.find(actor_token)
    if actor_idx < 0:
        return None
    action_match = _find_first_ordered_term(text, _ALL_ACTION_VERBS, start=actor_idx + len(actor_token), limit=28)
    if action_match is None:
        return None
    action_idx, action = action_match
    asset_match = _find_first_ordered_term(text, _BUSINESS_ASSETS, start=action_idx + len(action), limit=24)
    if asset_match is None:
        return None
    _, asset = asset_match
    return action, asset


def infer_turn_role_signal(text: str) -> TurnRoleSignal | None:
    value = str(text or "").strip()
    if not value:
        return None
    signal = _infer_actor_owner_signal(
        value,
        actor_token="\u6211",
        owner_token="\u4f60",
        actor="user",
        owner="assistant",
    )
    if signal is not None:
        return signal
    signal = _infer_actor_owner_signal(
        value,
        actor_token="\u4f60",
        owner_token="\u6211",
        actor="assistant",
        owner="user",
    )
    if signal is not None:
        return signal
    return None


def mentions_business_asset_of_assistant(text: str) -> bool:
    return _ASSISTANT_BUSINESS_ASSET_RE.search(str(text or "")) is not None


def mentions_business_asset_of_user(text: str) -> bool:
    return _USER_BUSINESS_ASSET_RE.search(str(text or "")) is not None


def has_authority_claim_over_user(text: str) -> bool:
    value = str(text or "")
    return any(pattern.search(value) for pattern in _AUTHORITY_PATTERNS)


def has_explicit_authority_grant(text: str) -> bool:
    value = str(text or "")
    return any(pattern.search(value) for pattern in _AUTHORITY_GRANT_PATTERNS)


def response_reverses_turn_actor(text: str, signal: TurnRoleSignal | None) -> bool:
    if signal is None:
        return False
    value = str(text or "")
    if signal.actor == "user" and signal.owner == "assistant":
        parsed = _find_actor_action_asset(value, actor_token="\u6211")
        if parsed is not None:
            action, asset = parsed
            if _normalize_action_family(action) == signal.action_family:
                return not signal.asset or asset == signal.asset
    if signal.actor == "assistant" and signal.owner == "user":
        parsed = _find_actor_action_asset(value, actor_token="\u4f60")
        if parsed is not None:
            action, asset = parsed
            if _normalize_action_family(action) == signal.action_family:
                return not signal.asset or asset == signal.asset
    return False
