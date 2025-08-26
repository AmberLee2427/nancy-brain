# hatch_hooks.py
import os
from hatchling.metadata.plugin.interface import MetadataHookInterface
from pathlib import Path


class CustomHook(MetadataHookInterface):
    def update(self, metadata):
        build_sha = os.environ.get("BUILD_SHA", "unknown")
        build_at = os.environ.get("BUILD_AT", "unknown")

        build_info_path = Path(__file__).parent / "nancy_brain" / "_build_info.py"
        with open(build_info_path, "w") as f:
            f.write(f'__build_sha__ = "{build_sha}"\n')
            f.write(f'__built_at__ = "{build_at}"\n')
