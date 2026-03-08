#!/usr/bin/env python3
"""Print one repo name per line from repositories.yml.

Usage:
    python3 scripts/cluster/list_repos.py [path/to/repositories.yml]

Used by the SLURM array job to map SLURM_ARRAY_TASK_ID → repo name.
"""

import sys
import yaml

config_path = sys.argv[1] if len(sys.argv) > 1 else "config/repositories.yml"

with open(config_path) as f:
    config = yaml.safe_load(f)

for entries in config.values():
    for repo in entries:
        print(repo["name"])
