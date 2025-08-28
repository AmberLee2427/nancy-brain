# hatch_hooks.py
import os
from pathlib import Path
from hatchling.metadata.plugin.interface import MetadataHookInterface


class CustomHook(MetadataHookInterface):
    def update(self, metadata):
        # Recreate authors dynamically (since we removed them from pyproject)
        metadata["authors"] = [{"name": "Amber Malpas", "email": "malpas.1@osu.edu"}]

        # Your build info side-effect
        build_sha = os.environ.get("BUILD_SHA", "unknown")
        build_at = os.environ.get("BUILD_AT", "unknown")
        out = Path.cwd() / "nancy_brain" / "_build_info.py"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f'__build_sha__ = "{build_sha}"\n__built_at__ = "{build_at}"\n')


def get_metadata_hook():
    return CustomHook
