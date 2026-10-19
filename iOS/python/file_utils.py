from pathlib import Path
from ios_bridge import manager


def get_audios_dir():
    return str(manager().documents / "Audio")


def get_documents_dir():
    return str(manager().documents / "Files")


def list_dir(path, extensions=None, recursive=False):
    root = Path(path).resolve()
    allowed = manager().documents.resolve()
    if not root.is_relative_to(allowed):
        return []  # Android shared-storage paths have no iOS equivalent.
    if not root.is_dir():
        return []
    suffixes = {x.lower() for x in extensions} if extensions else None
    return [str(p) for p in (root.rglob("*") if recursive else root.iterdir())
            if p.is_file() and p.resolve().is_relative_to(allowed)
            and (suffixes is None or p.suffix.lower() in suffixes)]
