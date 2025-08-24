#!/bin/bash
# Release script for nancy-brain
set -e

# Check if we're on main branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "❌ You must be on the main branch to release"
    exit 1
fi

# Check if working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Working directory is not clean. Commit or stash changes first."
    exit 1
fi

# Get the bump type from argument
BUMP_TYPE=${1:-patch}

if [ "$BUMP_TYPE" != "major" ] && [ "$BUMP_TYPE" != "minor" ] && [ "$BUMP_TYPE" != "patch" ]; then
    echo "❌ Invalid bump type. Use: major, minor, or patch"
    echo "Usage: $0 [major|minor|patch]"
    exit 1
fi

echo "🔍 Current version:"
bump-my-version show current_version

echo ""
echo "🚀 Bumping $BUMP_TYPE version and creating release..."

# Bump version, commit, and tag
bump-my-version bump $BUMP_TYPE

# Get the new version
NEW_VERSION=$(bump-my-version show current_version)

echo "✅ Version bumped to $NEW_VERSION"
echo "📤 Pushing to GitHub (this will trigger PyPI release)..."

# Push the commit and tag
git push origin main --tags

echo "🎉 Release $NEW_VERSION is complete!"
echo "📦 Check GitHub Actions for PyPI publishing status"
echo "🔗 https://github.com/AmberLee2427/nancy-brain/actions"
