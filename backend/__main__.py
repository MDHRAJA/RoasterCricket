"""Run a loopback-only development server: python -m backend [--port 8000]."""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Start the local IPL analytics API")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port between 1024 and 65535")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
