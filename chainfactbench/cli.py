from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .capture import capture_bundle
from .core import BenchError, atomic_write_text, dump_json, load_json_source, validate_bundle
from .rpc import RPCClient, RPCError
from .score import load_answers, render_table, score_answers


def _status(message: str) -> None:
    print(f"phase: {message}", file=sys.stderr, flush=True)


def _write_output(destination: str, text: str) -> None:
    if destination == "-":
        sys.stdout.write(text)
    else:
        atomic_write_text(destination, text)


def _prompt_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    block = bundle["block"]
    return [
        {
            "block_hash": block["hash"],
            "block_number": block["number"],
            "case_id": case["id"],
            "prompt": case["prompt"],
            "required_response": {
                "block_hash": "COPY_THE_PINNED_BLOCK_HASH",
                "block_number": "COPY_THE_PINNED_BLOCK_NUMBER",
                "case_id": "COPY_THE_CASE_ID",
                "value": "ANSWER_VALUE",
            },
        }
        for case in bundle["cases"]
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chainfactbench",
        description="Capture block-pinned EVM facts and score structured AI answers offline.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="validate a frozen evidence bundle")
    verify.add_argument("bundle", help="bundle JSON path or - for stdin")

    score = subparsers.add_parser("score", help="score answer JSONL against a bundle")
    score.add_argument("bundle", help="bundle JSON path")
    score.add_argument("answers", help="answer JSONL path or - for stdin")
    score.add_argument("--format", choices=("table", "json"), default="table")
    score.add_argument("--no-color", action="store_true")

    prompts = subparsers.add_parser("prompts", help="render model-input JSONL without expected values")
    prompts.add_argument("bundle", help="bundle JSON path")
    prompts.add_argument("output", nargs="?", default="-", help="output path or - for stdout")

    capture = subparsers.add_parser("capture", help="capture an evidence bundle through read-only RPC")
    capture.add_argument("spec", help="capture specification JSON path")
    capture.add_argument("output", help="new or replacement bundle path")
    capture.add_argument(
        "--rpc-url",
        help="RPC endpoint; otherwise read CHAINFACT_RPC_URL (never persisted or printed)",
    )
    capture.add_argument("--timeout", type=float, default=20.0)
    capture.add_argument("--max-response-bytes", type=int, default=4 * 1024 * 1024)

    subparsers.add_parser("demo", help="run the bundled offline scoring demonstration")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            bundle = validate_bundle(load_json_source(args.bundle))
            print(
                json.dumps(
                    {
                        "block_hash": bundle["block"]["hash"],
                        "block_number": bundle["block"]["number"],
                        "cases": len(bundle["cases"]),
                        "chain_id": bundle["chain_id"],
                        "valid": True,
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "capture":
            endpoint = args.rpc_url or os.environ.get("CHAINFACT_RPC_URL")
            if not endpoint:
                raise BenchError("capture requires --rpc-url or CHAINFACT_RPC_URL")
            spec = load_json_source(args.spec)
            client = RPCClient(endpoint, args.timeout, args.max_response_bytes)
            bundle = capture_bundle(spec, client, status=_status)
            atomic_write_text(args.output, dump_json(bundle))
            print(
                json.dumps(
                    {
                        "block_hash": bundle["block"]["hash"],
                        "block_number": bundle["block"]["number"],
                        "cases": len(bundle["cases"]),
                        "output": str(Path(args.output).name),
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "prompts":
            bundle = validate_bundle(load_json_source(args.bundle))
            text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in _prompt_rows(bundle))
            _write_output(args.output, text)
            return 0

        if args.command == "score":
            bundle = validate_bundle(load_json_source(args.bundle))
            report = score_answers(bundle, load_answers(args.answers))
            if args.format == "json":
                sys.stdout.write(dump_json(report))
            else:
                color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
                sys.stdout.write(render_table(report, color=color))
            return 0 if report["failed"] == 0 and not report["unexpected_answer_ids"] else 1

        if args.command == "demo":
            data = Path(__file__).resolve().parent / "data"
            bundle = validate_bundle(load_json_source(data / "demo_bundle.json"))
            report = score_answers(bundle, load_answers(data / "demo_answers.jsonl"))
            sys.stdout.write(render_table(report, color=False))
            return 0 if report["failed"] == 0 else 1
    except RPCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (BenchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
