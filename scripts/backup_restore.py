"""CLI for quiesced snapshots and isolated recovery."""

import argparse
import json
import os
from pathlib import Path

from realty.backups import backup, restore, verify_snapshot
from realty.config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "verify", "restore"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument(
        "--quiesced", action="store_true", help="Confirm API writes and workers are paused"
    )
    args = parser.parse_args()
    if args.operation == "backup":
        if not args.destination:
            parser.error("--destination is required")
        result = backup(settings.database_url, args.destination, args.quiesced)
    else:
        if not args.source:
            parser.error("--source is required")
        if args.operation == "restore":
            if not args.destination:
                parser.error("--destination is required")
            result = restore(args.source, args.destination, os.environ.get("RESTORE_DATABASE_URL"))
        else:
            manifest = verify_snapshot(args.source)
            result = {"verified": True, "files": len(manifest["files"])}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
