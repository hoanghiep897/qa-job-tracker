"""Daily opt-in browser scan; updates published JSON only on successful collection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tracker.browser_crawler import collect_browser
from tracker.export import build_dataset

def run(config: str, output: str, platform: str = "itviec",
        fetch=collect_browser) -> dict:
    boards = json.loads(Path(config).read_text(encoding="utf-8"))
    eligible = [b for b in boards if b.get("provider") == platform
                and b.get("browser_enabled") is True
                and b.get("enabled") is True]
    if not eligible:
        raise RuntimeError(f"No enabled browser board configured for {platform}")
    target = Path(output)
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    # build_dataset retains previously observed source records; on total failure
    # it raises without writing or losing the last successful snapshot.
    result = build_dataset(eligible, previous=previous, fetch=fetch)
    if result["sources_failed"]:
        raise RuntimeError("Browser collection failed: " + "; ".join(
            f'{x["source"]}: {x["error"]}' for x in result["sources_failed"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"Browser scan: {result['source_records_read']} detail pages parsed, "
          f"{len(result['jobs'])} observed QA records total.")
    return result

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/boards.json")
    ap.add_argument("--output", default="data/jobs.json")
    ap.add_argument("--platform", choices=("itviec", "topcv", "vietnamworks"),
                    default="itviec")
    args = ap.parse_args()
    run(args.config, args.output, args.platform)

if __name__ == "__main__":
    main()
