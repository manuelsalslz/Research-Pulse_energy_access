#!/usr/bin/env python3
"""Copy repo config/templates into the pip wheel bundle before publishing."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "research_agent" / "bundled"


def main() -> None:
    cfg_src = ROOT / "config"
    cfg_dst = BUNDLED / "config"
    tpl_src = ROOT / "templates"
    tpl_dst = BUNDLED / "templates"

    cfg_dst.mkdir(parents=True, exist_ok=True)
    tpl_dst.mkdir(parents=True, exist_ok=True)

    for name in ("topics.yaml", "settings.yaml", "subscribers.sample.csv", "core_venues.yaml"):
        shutil.copy2(cfg_src / name, cfg_dst / name)
        print(f"  synced config/{name}")

    shutil.copy2(tpl_src / "email.html.j2", tpl_dst / "email.html.j2")
    print("  synced templates/email.html.j2")
    print("Done. Ready to build: python -m build")


if __name__ == "__main__":
    main()
