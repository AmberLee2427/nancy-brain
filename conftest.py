import pathlib


def pytest_ignore_collect(path, config):
    """Prevent pytest from collecting files under the `knowledge_base` folder.

    This is a defensive measure so that running `pytest` in the repository will
    never attempt to collect or import the third-party/knowledge-base content
    that pulls in heavy optional packages.
    """
    try:
        p = pathlib.Path(path)
        parts = {p_part for p_part in p.parts}
        if "knowledge_base" in parts:
            return True
    except Exception:
        # If anything goes wrong, don't block collection elsewhere
        return False
