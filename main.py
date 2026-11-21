import argparse
import json
import os
import sys

from ticket_approver import HttpAiClassifier, load_tickets, process_tickets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Triage customer support tickets")
    parser.add_argument("input", help="Ticket file (.json, .jsonl, or .csv)")
    parser.add_argument("-o", "--output", help="Write the final report to this JSON file")
    parser.add_argument("--endpoint", help="AI classification endpoint")
    parser.add_argument("--api-key", help="API key for the AI endpoint")
    parser.add_argument("--model", help="Optional model name sent to the endpoint")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--confidence", type=float, default=80.0)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    endpoint = args.endpoint or os.getenv("TICKET_AI_ENDPOINT")
    if not endpoint:
        print("error: provide --endpoint or set TICKET_AI_ENDPOINT", file=sys.stderr)
        return 2

    tickets = load_tickets(args.input)
    classifier = HttpAiClassifier(
        endpoint,
        api_key=args.api_key or os.getenv("TICKET_AI_API_KEY"),
        model=args.model,
    )
    report = process_tickets(
        tickets,
        classifier,
        timeout=args.timeout,
        confidence_threshold=args.confidence / 100.0,
    )

    rendered = json.dumps(report, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as destination:
            destination.write(rendered)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
