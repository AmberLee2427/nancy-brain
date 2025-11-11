from pathlib import Path


def pytest_ignore_collect(collection_path: Path, config):
    """Prevent pytest from collecting files under the `knowledge_base` folder.

    This is a defensive measure so that running `pytest` in the repository will
    never attempt to collect or import the third-party/knowledge-base content
    that pulls in heavy optional packages.
    """
    try:
        # Path.parts handles cross-platform separators; convert to set for contains check.
        parts = set(collection_path.parts)
        if "knowledge_base" in parts:
            return True
    except Exception:
        # If anything goes wrong, don't block collection elsewhere
        return False
