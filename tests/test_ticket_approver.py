import unittest

from ticket_approver import process_tickets, triage_ticket


class TicketApproverTests(unittest.TestCase):
    def test_auto_triage_confident_ticket(self):
        result = triage_ticket(
            {"text": "I need a copy of my latest invoice"},
            lambda ticket: {"category": "Billing", "priority": "Medium", "confidence": 95},
        )
        self.assertEqual(result["pile"], "auto_triaged")
        self.assertEqual(result["reasons"], [])

    def test_low_confidence_goes_to_human_review(self):
        result = triage_ticket(
            {"text": "The dashboard looks wrong"},
            lambda ticket: {"category": "Bug", "priority": "Medium", "confidence": 55},
        )
        self.assertEqual(result["pile"], "human_review")
        self.assertIn("low_confidence", result["reasons"])

    def test_api_error_goes_to_human_review(self):
        def fail(ticket):
            raise RuntimeError("AI unavailable")

        result = triage_ticket({"text": "Account access problem"}, fail)
        self.assertEqual(result["pile"], "human_review")
        self.assertIn("api_error", result["reasons"])

    def test_timeout_goes_to_human_review(self):
        def slow(ticket):
            import time
            time.sleep(0.1)
            return {"category": "Bug", "priority": "High", "confidence": 99}

        result = triage_ticket({"text": "The app is broken"}, slow, timeout=0.01)
        self.assertEqual(result["pile"], "human_review")
        self.assertIn("timeout", result["reasons"])

    def test_obvious_emergency_overrides_low_ai_priority(self):
        result = triage_ticket(
            {"text": "The production system is down and users cannot sign in"},
            lambda ticket: {"category": "Bug", "priority": "Low", "confidence": 99},
        )
        self.assertEqual(result["pile"], "human_review")
        self.assertIn("obvious_emergency", result["reasons"])

    def test_report_counts_and_reason_totals(self):
        tickets = [
            {"text": "Invoice question"},
            {"text": "We have been hacked"},
            {"text": "Cannot log in"},
        ]
        report = process_tickets(
            tickets,
            lambda ticket: (
                {"category": "Security", "priority": "Low", "confidence": 50}
                if "hacked" in ticket["text"]
                else {"category": "Account", "priority": "High", "confidence": 90}
            ),
        )
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["auto_triaged"], 2)
        self.assertEqual(report["human_review"], 1)
        self.assertEqual(report["reason_counts"]["obvious_emergency"], 1)


if __name__ == "__main__":
    unittest.main()
