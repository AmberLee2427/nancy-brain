#!/usr/bin/env python3
"""
Repository Management Script for Roman Galactic Exoplanet Survey Slack Bot

This script manages the cloning and updating of repositories for the knowledge base.
It supports both initial cloning and refreshing existing repositories.
"""

import os
import sys
import subprocess
import argparse
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RepositoryManager:
    def __init__(self, base_path: str = "knowledge_base/raw"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def load_config(self, config_file: str) -> Dict:
        """Load repository configuration from YAML file."""
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                return yaml.safe_load(f)

    def save_config(self, config: Dict, config_file: str):
        """Save repository configuration to YAML file."""
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)

    def run_command(self, command: List[str], cwd: Optional[str] = None) -> bool:
        """Run a shell command and return success status."""
        try:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(command)}")
            logger.error(f"Error: {e.stderr}")
            return False

    def clone_repository(self, repo_info: Dict, category: str) -> bool:
        """Clone a single repository."""
        repo_name = repo_info["name"]
        repo_url = repo_info["url"]
        repo_path = self.base_path / category / repo_name

        logger.info(f"Processing {category}/{repo_name}...")

        if repo_path.exists():
            logger.info(f"Repository {repo_name} already exists. Updating...")
            return self.update_repository(repo_path)
        else:
            logger.info(f"Cloning {repo_name} from {repo_url}...")
            repo_path.parent.mkdir(parents=True, exist_ok=True)

            if self.run_command(["git", "clone", repo_url, str(repo_path)]):
                logger.info(f"Successfully cloned {repo_name}")
                return True
            else:
                logger.error(f"Failed to clone {repo_name}")
                return False

    def update_repository(self, repo_path: Path) -> bool:
        """Update an existing repository."""
        try:
            # Fetch latest changes
            if not self.run_command(["git", "fetch", "--all"], cwd=str(repo_path)):
                return False

            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            current_branch = result.stdout.strip()

            # Pull latest changes
            if self.run_command(["git", "pull", "origin", current_branch], cwd=str(repo_path)):
                logger.info(f"Successfully updated {repo_path.name}")
                return True
            else:
                logger.error(f"Failed to update {repo_path.name}")
                return False

        except Exception as e:
            logger.error(f"Error updating {repo_path.name}: {e}")
            return False

    def process_category(self, category: str, repos: List[Dict]) -> int:
        """Process all repositories in a category."""
        logger.info(f"\n=== Processing {category} ===")
        success_count = 0
        for repo_info in repos:
            if self.clone_repository(repo_info, category):
                success_count += 1
        logger.info(f"Completed {category}: {success_count}/{len(repos)} repositories successful")
        return success_count

    def process_all(self, config: Dict) -> Dict[str, int]:
        """Process all repositories in the configuration."""
        results = {}
        total_success = 0
        total_repos = 0
        for category, repos in config.items():
            if isinstance(repos, list):
                success_count = self.process_category(category, repos)
                results[category] = success_count
                total_success += success_count
                total_repos += len(repos)

        logger.info("\n=== Summary ===")
        logger.info(f"Total repositories processed: {total_repos}")
        logger.info(f"Successful: {total_success}")
        logger.info(f"Failed: {total_repos - total_success}")

        return results

    def list_repositories(self, config: Dict):
        """List all configured repositories."""
        logger.info("Configured repositories:")
        for category, repos in config.items():
            if isinstance(repos, list):
                logger.info(f"\n{category}:")
                for repo in repos:
                    status = "✓" if (self.base_path / category / repo["name"]).exists() else "✗"
                    logger.info(f"  {status} {repo['name']} ({repo['description']})")

    def clean_repositories(self, config: Dict, dry_run: bool = False):
        """Remove repositories that are no longer in the configuration."""
        logger.info("Checking for orphaned repositories...")

        for category_dir in self.base_path.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                if category in config:
                    # Check each repo in the category directory
                    for repo_dir in category_dir.iterdir():
                        if repo_dir.is_dir():
                            repo_name = repo_dir.name
                            # Check if this repo is still in config
                            repos_in_config = [repo["name"] for repo in config[category]]
                            if repo_name not in repos_in_config:
                                if dry_run:
                                    logger.info(f"Would remove orphaned repo: {category}/{repo_name}")
                                else:
                                    logger.info(f"Removing orphaned repo: {category}/{repo_name}")
                                    import shutil

                                    shutil.rmtree(repo_dir)


def main():
    parser = argparse.ArgumentParser(description="Manage repositories for the knowledge base")
    parser.add_argument(
        "--config",
        default="config/repositories.yml",
        help="Path to repository configuration file",
    )
    parser.add_argument("--base-path", default="knowledge_base/raw", help="Base path for repositories")
    parser.add_argument("--list", action="store_true", help="List all configured repositories")
    parser.add_argument("--clean", action="store_true", help="Remove repositories not in configuration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument("--category", help="Process only a specific category")
    args = parser.parse_args()

    manager = RepositoryManager(args.base_path)

    # Load configuration
    config = manager.load_config(args.config)

    if args.list:
        manager.list_repositories(config)
        return

    if args.clean:
        manager.clean_repositories(config, dry_run=args.dry_run)
        return

    # Process repositories
    if args.category:
        if args.category in config:
            repos = config[args.category]
            if isinstance(repos, list):
                manager.process_category(args.category, repos)
            else:
                logger.error(f"Invalid category configuration for {args.category}")
        else:
            logger.error(f"Category '{args.category}' not found in configuration")
    else:
        manager.process_all(config)

    # Save updated configuration
    if not args.dry_run:
        manager.save_config(config, args.config)


if __name__ == "__main__":
    main()
