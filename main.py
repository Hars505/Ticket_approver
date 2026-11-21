import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx

from src.classifier import AsyncClassifier, ClassifierConfig, OfflineClassifier
from src.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Async Support Ticket Triage Pipeline with deterministic guardrails."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/tickets.json"),
        help="Path to input tickets JSON or CSV file (default: data/tickets.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory to save triaged.json, human_review.json, and report.md (default: output)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Maximum concurrent classification tasks (default: 10)",
    )
    parser.add_argument(
        "--simulate-failures",
        type=float,
        default=0.0,
        help="Failure simulation rate between 0.0 and 1.0 (default: 0.0)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run offline using deterministic local heuristics without remote LLM API calls",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Per-request timeout in seconds (default: 8.0)",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI REST backend server for the frontend",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the API server on (default: 8000)",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    load_dotenv()
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    use_offline = args.offline or not api_key

    if use_offline:
        print("[INFO] Running in OFFLINE mode using local deterministic classifier.")
        classifier = OfflineClassifier(failure_rate=args.simulate_failures)
        result = await run_pipeline(
            input_path=args.input,
            output_dir=args.output_dir,
            classifier=classifier,
            concurrency=args.concurrency,
        )
    else:
        print(f"[INFO] Running in ONLINE mode using model: {model} at {base_url}")
        config = ClassifierConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=args.timeout,
        )
        async with httpx.AsyncClient() as client:
            classifier = AsyncClassifier(
                client=client,
                config=config,
                failure_rate=args.simulate_failures,
            )
            result = await run_pipeline(
                input_path=args.input,
                output_dir=args.output_dir,
                classifier=classifier,
                concurrency=args.concurrency,
            )

    total = len(result.triaged) + len(result.human_review)
    triaged_pct = (len(result.triaged) / total * 100) if total > 0 else 0.0
    review_pct = (len(result.human_review) / total * 100) if total > 0 else 0.0

    print("=" * 60)
    print("SUPPORT TICKET TRIAGE SUMMARY")
    print("=" * 60)
    print(f"Total Tickets Processed: {total}")
    print(f"Triaged (Automated)    : {len(result.triaged)} ({triaged_pct:.1f}%)")
    print(f"Human Review (Escalated): {len(result.human_review)} ({review_pct:.1f}%)")
    print(f"Total Runtime          : {result.total_runtime_seconds:.2f} seconds")
    print(f"Outputs written to     : {args.output_dir.resolve()}")
    print("=" * 60)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.serve:
        import uvicorn
        print(f"[INFO] Starting Support Ticket Triage API server on http://localhost:{args.port}...")
        uvicorn.run("src.api:app", host="0.0.0.0", port=args.port, reload=True)
        return

    try:
        sys.exit(asyncio.run(_main_async(args)))
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
    except Exception as err:
        print(f"\n[ERROR] Pipeline failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

