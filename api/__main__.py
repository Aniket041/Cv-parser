"""Run the CV parser API: `python -m api`."""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address. The default keeps candidate data on this machine; "
                             "0.0.0.0 exposes personal data to your network.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Reload on code changes (development).")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"WARNING: binding to {args.host} exposes candidate personal data beyond this machine.")
    print(f"CV parser API on http://{args.host}:{args.port}  (interactive docs at /docs)")
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
