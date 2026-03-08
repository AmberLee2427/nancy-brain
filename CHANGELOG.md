# Changelog

## [0.2.1] - 2026-03-07

### Added
- `nancy-brain import-bibtex -f references.bib` — import articles from a BibTeX file into `articles.yml` via arXiv metadata enrichment.
- `nancy-brain import-ads --library "My Library"` — import articles from an ADS private library into `articles.yml` via the ADS API.
- `nancy-brain import-env -f environment.yml` — scan a conda environment file and add GitHub-backed packages to `repositories.yml`.
- `--repo` option for `nancy-brain build` to limit processing to a single named repository.
- Optional `ref:` field per entry in `repositories.yml` for reproducible knowledge-base builds (pin to a branch, tag, or full commit SHA).
- `NB_SUMMARY_MODEL` environment variable for local summary model selection (default: `Qwen/Qwen2.5-Coder-0.5B-Instruct`).
- `NB_MIN_SUMMARY_CHARS` environment variable to tune small-file summary skip threshold (default: 200).
- `bibtexparser>=2.0.0b7` added as a core dependency (required for BibTeX import).

### Changed
- Summary generation now skips files shorter than `NB_MIN_SUMMARY_CHARS` (default 200 chars).
- Summary generation now skips known data/binary file extensions (`.fits`, `.npy`, `.csv`, `.pkl`, `.hdf5`, `.h5`, `.mat`, `.nii`, `.gz`, `.so`, images, etc.).
- `clone_repositories` and `update_repository` are now ref-aware: named refs use shallow clones (`--branch ref --depth 1`); full commit SHAs trigger a full clone + checkout.

### Fixed
- `import-env`: packages with no `project_urls` but a GitHub URL in `home_page` (common in pre-2020 PyPI packages) are now correctly imported instead of silently skipped.
- `import-bibtex` / `import-ads`: arXiv error-feed responses (HTTP 200 with an Atom `<entry>` titled "Error") are no longer mistaken for valid paper entries, preventing broken URLs from being written to `articles.yml`.
