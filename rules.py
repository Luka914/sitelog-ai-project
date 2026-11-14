from schemas import FlaggedIssue
from db import get_past_issue_count

# Deterministic SLA mapping: AI never invents deadlines; Python enforces company policy
SLA_BY_PRIORITY = {
    "CRITICAL": "4 Hours (Immediate Lockout Required)",
    "HIGH": "24 Hours (Before Next Shift)",
    "MEDIUM": "7 Days (Scheduled Maintenance)",
    "LOW": "14 Days (Routine Check)",
}

def evaluate_ticket_rules(
    asset_id: str,
    signature_present: bool,
    issue: FlaggedIssue
) -> dict:
    """Applies hard-coded safety rules, historical escalation, and Responsible AI gates."""
    priority = issue.severity_hint
    reasons = []

    # Rule 1: Historical Pattern Escalation (Memory across paper forms)
    past_count = get_past_issue_count(asset_id)
    if past_count >= 2 and priority != "CRITICAL":
        priority = "CRITICAL"
        reasons.append(f"Auto-escalated: {past_count} prior warnings logged on {asset_id}")

    # Rule 2: Explicit FAIL checkbox always requires at least HIGH priority
    if issue.status == "FAIL" and priority in ("LOW", "MEDIUM"):
        priority = "HIGH"
        reasons.append("Checklist item explicitly marked FAIL")

    # Rule 3: Compliance audit check for missing inspector signature
    if not signature_present:
        reasons.append("AUDIT FLAG: Inspector signature missing on physical form")

    # Rule 4: Responsible AI Confidence Gate (Never guess illegible handwriting)
    if issue.confidence < 0.75:
        ticket_status = "NEEDS_HUMAN_REVIEW"
        reasons.append(f"Low OCR confidence ({int(issue.confidence * 100)}%) — verify handwriting")
    else:
        ticket_status = "PENDING_APPROVAL"

    if not reasons:
        reasons.append("Standard single-incident triage")

    return {
        "priority": priority,
        "sla_deadline": SLA_BY_PRIORITY[priority],
        "escalation_reason": " | ".join(reasons),
        "status": ticket_status,
    }