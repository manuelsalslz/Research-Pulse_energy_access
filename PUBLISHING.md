# Publishing ResearchPulse to PyPI

## Prerequisites

1. [PyPI account](https://pypi.org/account/register/) (free)
2. [Trusted publishing](https://docs.pypi.org/trusted-publishers/) **or** an API token

## One-time setup

```bash
pip install build twine
```

## Before each release

1. Bump version in `research_agent/__init__.py` and `pyproject.toml` (keep in sync).
2. Sync bundled config into the wheel:

   ```bash
   python scripts/sync_bundled.py
   ```

3. Build and verify locally:

   ```bash
   python -m build
   pip install dist/research_pulse-*.whl --force-reinstall
   research-pulse help
   ```

4. Tag and push (optional, for GitHub Actions):

   ```bash
   git tag v0.4.1
   git push origin v0.4.1
   ```

## Publish manually (API token)

Create a token at https://pypi.org/manage/account/token/ (scope: entire account or project `research-pulse`).

```bash
python -m twine upload dist/*
# Username: __token__
# Password: pypi-AgEIcHlwaS5vcmcC...
```

Or non-interactive:

```bash
TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-... python -m twine upload dist/*
```

## Publish via GitHub Actions

Push a tag `v*` (e.g. `v0.4.1`). The workflow `.github/workflows/publish-pypi.yml` builds and uploads to PyPI when you configure a trusted publisher on PyPI for this repo.

## After install (users)

```bash
pip install research-pulse
research-pulse              # daily digest
research-pulse search "CRISPR"
research-pulse config papers 10
```

User data lives in `~/.research-pulse/` (config, cache, memory, previews).

## Package name

PyPI project: **research-pulse**  
CLI commands: `research-pulse` and `rp`
