"""Helpers for preloading local embedding models during install/setup."""

from __future__ import annotations

import argparse

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def ensure_local_embedding_model(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    *,
    download_if_missing: bool = True,
) -> tuple[bool, str]:
    """Ensure the sentence-transformers model is available in the local cache."""

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        return False, f"sentence-transformers unavailable: {exc}"

    try:
        model = SentenceTransformer(model_name, local_files_only=True)
        dim = model.get_sentence_embedding_dimension()
        return True, f"embedding model already cached: {model_name} ({dim} dims)"
    except Exception as local_exc:
        if not download_if_missing:
            return False, f"embedding model not cached locally: {model_name} ({local_exc})"

    try:
        model = SentenceTransformer(model_name)
        dim = model.get_sentence_embedding_dimension()
        return True, f"embedding model downloaded: {model_name} ({dim} dims)"
    except Exception as exc:
        return False, f"failed to download embedding model {model_name}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preload the local embedding model cache.")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="sentence-transformers model name")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only verify the local cache; do not download when missing.",
    )
    args = parser.parse_args()

    ok, message = ensure_local_embedding_model(
        args.model,
        download_if_missing=not args.local_only,
    )
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
