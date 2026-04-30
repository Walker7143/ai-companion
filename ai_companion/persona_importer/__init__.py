"""Book-to-persona importer.

This package turns one long-form book into reviewable persona JSON drafts for
multiple target characters. The importer deliberately writes drafts first; a
separate apply step copies reviewed files into the active bot data directory.
"""

from .schema import CharacterTarget, ImportOptions

__all__ = ["CharacterTarget", "ImportOptions"]
