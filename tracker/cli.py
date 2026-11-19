"""Command-line interface: python -m tracker.cli [collect|import-csv|seed-demo]."""
import argparse
import json
from pathlib import Path
from .core import connect, fetch_board, import_csv, save_job

DEMO = [
    {"source":"demo","source_id":"1","company":"Example Tech","title":"QA Automation Engineer",
     "location":"Hà Nội","url":"","description":"Playwright TypeScript API Testing GitHub Actions"},
    {"source":"demo","source_id":"2","company":"Sample Software","title":"Manual QA Tester",
     "location":"TP. Hồ Chí Minh","url":"","description":"Postman SQL manual testing"},
    {"source":"demo","source_id":"3","company":"Demo Labs","title":"Senior SDET",
     "location":"Remote","url":"","description":"Python Selenium Docker Jenkins LLM evaluation"},
]

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["collect", "import-csv", "seed-demo"])
    p.add_argument("--db", default="data/jobs.db")
    p.add_argument("--config", default="config/boards.json")
    p.add_argument("--file", help="CSV path for import-csv")
    args = p.parse_args()
    db = connect(args.db)
    if args.command == "seed-demo":
        for item in DEMO:
            save_job(db, item, demo=True)
        print(f"Seeded {len(DEMO)} clearly labeled DEMO jobs")
    elif args.command == "import-csv":
        if not args.file:
            p.error("--file is required for import-csv")
        print(f"Imported {import_csv(db, args.file)} rows")
    else:
        config = Path(args.config)
        if not config.is_file():
            p.error(f"Create {config} from config/boards.example.json first")
        boards = json.loads(config.read_text(encoding="utf-8"))
        total = 0
        for board in boards:
            try:
                items = fetch_board(board)
                for item in items:
                    save_job(db, item)
                print(f"{board['provider']}:{board['board']} -> {len(items)} jobs")
                total += len(items)
            except Exception as exc:
                print(f"ERROR {board.get('provider')}:{board.get('board')}: {exc}")
        print(f"Processed {total} job observations")

if __name__ == "__main__":
    main()
