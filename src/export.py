"""Export chart-ready CSVs: one per query in sql/exports/.

    python -m src.export --out exports

The daily workflow publishes these files to the repo's `data` branch, where
charting tools (e.g. Datawrapper) read them by URL and refresh automatically.
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Connection, text

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

QUERIES_DIR = PROJECT_ROOT / "sql" / "exports"


def export_all(conn: Connection, out_dir: Path) -> list[Path]:
    """Run each export query and write <name>.csv to out_dir; return the files written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for query_file in sorted(QUERIES_DIR.glob("*.sql")):
        df = pd.read_sql(text(query_file.read_text()), conn)
        path = out_dir / f"{query_file.stem}.csv"
        df.to_csv(path, index=False)
        logger.info("Wrote %s (%d rows)", path, len(df))
        written.append(path)
    if not written:
        raise FileNotFoundError(f"No .sql files in {QUERIES_DIR}")
    return written


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Export chart-ready CSVs.")
    parser.add_argument("--out", type=Path, default=Path("exports"), help="output folder (default: exports)")
    args = parser.parse_args(argv)

    from src.load import get_engine
    with get_engine().connect() as conn:
        export_all(conn, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
