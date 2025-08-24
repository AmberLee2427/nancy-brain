#!/usr/bin/env python3
"""
PDF Articles Management Script for Nancy's Knowledge Base

This script manages the downloading of PDF articles for the knowledge base.
It supports both initial downloading and refreshing existing articles.
"""

import os
import sys
import argparse
import yaml
import requests
from pathlib import Path
from typing import Dict, List, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PDFArticleManager:
    def __init__(self, base_path: str = "knowledge_base/raw"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def load_config(self, config_file: str) -> Dict:
        """Load PDF articles configuration from YAML file."""
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                return yaml.safe_load(f)
        return {}

    def save_config(self, config: Dict, config_file: str):
        """Save PDF articles configuration to YAML file."""
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)

    def download_article(self, article_info: Dict, category: str) -> bool:
        """Download a single PDF article."""
        article_name = article_info["name"]
        article_url = article_info["url"]
        article_path = self.base_path / category / f"{article_name}.pdf"

        logger.info(f"Processing {category}/{article_name}...")

        if article_path.exists():
            logger.info(f"Article {article_name}.pdf already exists. Skipping...")
            return True

        logger.info(f"Downloading {article_name} from {article_url}...")
        article_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(article_url, stream=True, timeout=30)
            response.raise_for_status()

            with open(article_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Successfully downloaded {article_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to download {article_name}: {e}")
            # Clean up partial download
            if article_path.exists():
                article_path.unlink()
            return False

    def update_article(self, article_path: Path) -> bool:
        """Re-download an existing article."""
        logger.info(f"Re-downloading {article_path.name}...")
        # For PDFs, we just delete and re-download since they don't have version control
        try:
            article_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Error preparing to re-download {article_path.name}: {e}")
            return False

    def process_category(self, category: str, articles: List[Dict], force_update: bool = False) -> int:
        """Process all articles in a category."""
        logger.info(f"\n=== Processing {category} ===")
        success_count = 0

        for article_info in articles:
            article_name = article_info["name"]
            article_path = self.base_path / category / f"{article_name}.pdf"

            if article_path.exists() and force_update:
                if self.update_article(article_path):
                    # Re-download
                    if self.download_article(article_info, category):
                        success_count += 1
                else:
                    logger.error(f"Failed to update {article_name}")
            else:
                if self.download_article(article_info, category):
                    success_count += 1

        logger.info(f"Completed {category}: {success_count}/{len(articles)} articles successful")
        return success_count

    def process_all(self, config: Dict, force_update: bool = False) -> Dict[str, int]:
        """Process all articles in the configuration."""
        results = {}
        total_success = 0
        total_articles = 0

        for category, articles in config.items():
            if isinstance(articles, list):
                success_count = self.process_category(category, articles, force_update)
                results[category] = success_count
                total_success += success_count
                total_articles += len(articles)

        logger.info("\n=== Summary ===")
        logger.info(f"Total articles processed: {total_articles}")
        logger.info(f"Successful: {total_success}")
        logger.info(f"Failed: {total_articles - total_success}")

        return results

    def list_articles(self, config: Dict):
        """List all configured articles."""
        logger.info("Configured PDF articles:")
        for category, articles in config.items():
            if isinstance(articles, list):
                logger.info(f"\n{category}:")
                for article in articles:
                    article_path = self.base_path / category / f"{article['name']}.pdf"
                    status = "✓" if article_path.exists() else "✗"
                    logger.info(f"  {status} {article['name']} - {article['description']}")

    def clean_articles(self, config: Dict, dry_run: bool = False):
        """Remove articles that are no longer in the configuration."""
        logger.info("Checking for orphaned PDF articles...")

        for category_dir in self.base_path.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                if category in config:
                    # Check each PDF in the category directory
                    for pdf_file in category_dir.glob("*.pdf"):
                        article_name = pdf_file.stem
                        # Check if this article is still in config
                        articles_in_config = [article["name"] for article in config[category]]
                        if article_name not in articles_in_config:
                            if dry_run:
                                logger.info(f"Would remove orphaned article: {category}/{article_name}.pdf")
                            else:
                                logger.info(f"Removing orphaned article: {category}/{article_name}.pdf")
                                pdf_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="Manage PDF articles for the knowledge base")
    parser.add_argument(
        "--config",
        default="config/articles.yml",
        help="Path to PDF articles configuration file",
    )
    parser.add_argument("--base-path", default="knowledge_base/raw", help="Base path for PDF articles")
    parser.add_argument("--list", action="store_true", help="List all configured PDF articles")
    parser.add_argument("--clean", action="store_true", help="Remove PDF articles not in configuration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument("--category", help="Process only a specific category")
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Re-download articles even if they exist",
    )
    args = parser.parse_args()

    manager = PDFArticleManager(args.base_path)

    # Load configuration
    config = manager.load_config(args.config)
    if not config:
        logger.error(f"No configuration found at {args.config}")
        return

    if args.list:
        manager.list_articles(config)
        return

    if args.clean:
        manager.clean_articles(config, dry_run=args.dry_run)
        return

    # Process articles
    if args.dry_run:
        logger.info("[DRY RUN] Would download PDF articles")
        for category, articles in config.items():
            if args.category and category != args.category:
                continue
            if isinstance(articles, list):
                logger.info(f"\n{category}:")
                for article in articles:
                    article_path = manager.base_path / category / f"{article['name']}.pdf"
                    action = "re-download" if (article_path.exists() and args.force_update) else "download"
                    logger.info(f"  Would {action}: {article['name']}")
        return

    if args.category:
        if args.category in config:
            articles = config[args.category]
            if isinstance(articles, list):
                manager.process_category(args.category, articles, args.force_update)
            else:
                logger.error(f"Invalid category configuration for {args.category}")
        else:
            logger.error(f"Category '{args.category}' not found in configuration")
    else:
        manager.process_all(config, args.force_update)

    # Save updated configuration
    if not args.dry_run:
        manager.save_config(config, args.config)


if __name__ == "__main__":
    main()
