import importlib
import sys


def test_cli_import_does_not_load_txtai_or_torch(monkeypatch):
    """Importing `nancy_brain.cli` should not cause new heavy imports (txtai/torch).

    The test records the set of loaded modules before import, imports the CLI module
    fresh, then asserts that no newly-added module belongs to txtai or torch.
    This helps catch regressions where heavy ML libs are imported at module scope.
    """
    # Ensure a fresh import
    for name in list(sys.modules.keys()):
        if name.startswith("nancy_brain.cli"):
            del sys.modules[name]

    before = set(sys.modules.keys())

    # Import (or reload) the CLI module
    try:
        mod = importlib.import_module("nancy_brain.cli")
        importlib.reload(mod)
    except Exception:
        # If import fails for unrelated reasons, make test fail with helpful message
        raise

    after = set(sys.modules.keys())
    new = after - before

    # Fail if any newly imported module is txtai/torch or their subpackages
    heavy_prefixes = ("txtai", "torch")
    newly_heavy = [m for m in new if any(m == p or m.startswith(p + ".") for p in heavy_prefixes)]

    assert not newly_heavy, f"Heavy modules imported during CLI import: {newly_heavy}"
