# Ticket_approver

A safety-first ticket triage command for JSON, JSONL, and CSV files.

```bash
python3 main.py tickets.json --endpoint https://ai.example.com/classify
python3 main.py tickets.csv --endpoint https://ai.example.com/classify --output report.json
```

Set `TICKET_AI_ENDPOINT` instead of passing `--endpoint`, and optionally set
`TICKET_AI_API_KEY`. The endpoint receives a JSON object containing `ticket`
and `text`, and should return `category`, `priority`, and `confidence`.

Confidence below 80% is sent for human review. Timeouts and API errors are
always sent for human review. Tickets containing obvious emergency language
are reviewed when the AI does not mark their priority as urgent.