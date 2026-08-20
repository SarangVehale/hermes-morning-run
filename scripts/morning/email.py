"""Real Email stream — replaces email_stub.py.

For each of the 4 gmail_* accounts, query Gmail API for recent unread
messages. Aggregate, score, sort. Top 5 → Brief 'Email' section. Positions
6+ → `📥 Email Triage.md` overflow.

Each rendered email is a markdown checkbox so the user can tick from Obsidian
mobile without losing the Gmail-app link:

    - [ ] [acct] From [[Sender Name]] — [Subject](gmail-deep-link)
"""
from __future__ import annotations

import datetime
import re
import sys
import urllib.parse
from dataclasses import dataclass
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from . import google, vault


GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

ACCOUNT_TAG = {
    "gmail_personal": "personal",
    "gmail_work":     "work",
    "gmail_iitm":     "iitm",
    "gmail_nfsu":     "nfsu",
}

# Importance signals — substring match on subject/snippet, case-insensitive.
_URGENCY_KEYWORDS = (
    "urgent", "asap", "action required", "deadline", "today", "tomorrow",
    "by end of day", "eod", "reminder", "approval", "please review",
    "please confirm", "blocker", "outage", "expires", "expiry",
)
_TOP_N_FOR_BRIEF = 5

# Junk-sender signals. Marketing, job-board notifications, social network
# nudges, recruiter spam — never important enough to be in the top 5 even
# when unread. Matched against sender email + subject (case-insensitive).
_JUNK_DOMAINS = (
    # Job-board / recruiter spam
    "linkedin.com", "seek.com.au", "indeed.com", "naukri.com",
    "glassdoor.com", "monster.com", "ziprecruiter.com",
    "fraunhofer-jobnotification", "hired.com", "wellfound.com",
    "angellist", "instahyre.com",
    # Common no-reply/marketing patterns
    "noreply@", "no-reply@", "notifications@", "newsletter@",
    "deals@", "promotions@", "marketing@", "info@", "offers@",
    "promo@", "noreply.", "do-not-reply@", "donotreply@",
    "support@", "billing@", "membership@", "rewards@", "alerts@",
    # Travel / booking promos
    "indigo.in", "goindigo.in", "@goindigo", "makemytrip.com",
    "booking.com", "airbnb.com", "agoda.com", "cleartrip.com",
    "yatra.com", "easemytrip.com", "trivago.com", "skyscanner",
    "expedia.com", "kayak.com", "ixigo.com", "redbus.in",
    # Airline + loyalty programs (Maharaja Club is Air India)
    "airindia.in", "vistara.com", "akasa.com",
    # Food + commerce promos
    "swiggy.com", "zomato.com", "amazon.in@", "flipkart.com",
    "myntra.com", "bigbasket.com", "blinkit.com", "zepto.com",
    "nutrabay.com", "tripmachine", "tripmachinecompany",
    # Banks: routine transaction notifications (not "fraud alert" / "OTP")
    "bankofmaharashtra.in", "sbi.co.in", "hdfcbank.com",
    "icicibank.com", "axisbank.com", "kotak.com",
    # Telecom promos
    "airtel.in", "jio.com", "vi.in",
    # Subscription/SaaS marketing
    "substack.com", "medium.com", "twilio.com", "calendly.com",
    "atlassian.com", "github.com noreply",
    # Webinar / event promo
    "webinarjam", "eventbrite",
    # Social network digests
    "instagram.com", "facebookmail.com", "twitter.com", "x.com",
    # Tech-skill marketing newsletters (different from genuine course content)
    "letsgetrusty", "lets-get-rusty", "scaler.com", "interviewbit.com",
    # Misc course/cert marketing
    "code-in-place", "codeinplace.stanford.edu", "stanford.edu codeinplace",
    # Recruiting outreach without a deadline (still want fraud/security through)
    "talentacquisition", "talent.acquisition",
)
_JUNK_SUBJECT_PATTERNS = (
    # Connection / job spam
    "new invitation", "new invitations", "i want to connect",
    "connection request", "wants to connect with you",
    "trending jobs", "jobs for you", "recommended for you",
    "stand out", "complete your profile", "profile views",
    "you appeared in", "search appearances",
    # Recruiting-aimed marketing (not actual interview invites)
    "could land on your cv", "land on your cv", "boost your cv",
    "stand out to recruiters", "this ai challenge",
    # Newsletters / digests
    "weekly digest", "your weekly", "newsletter", "daily digest",
    "what's new this week", "weekly roundup", "monthly digest",
    "something big is happening",  # rust newsletter style
    # Course / workshop / cert marketing
    "is live!", "is live!!", "is live!!!", "are live!", "are live!!",
    "course is live", "workshop is live", "now live",
    "check ", "check your ", "set your preferred name",
    "certificate eligibility", "certificate eligiblity",  # typo'd commonly
    "course access update", "update your profile",
    "hurry!!", "registration open",
    # Travel promos
    "escape awaits", "limited offer", "flash sale", "book now",
    "your getaway", "trip ideas", "exclusive deal", "fly with",
    "off on flights", "free cancellation",
    "experienced rider", "what every", "rider packs",
    # Bank transaction notifications (not actionable, just informational)
    "transaction with", "transaction alert", "txn alert",
    "debited from", "credited to", "amount debited",
    "amount credited", "upi transaction", "transaction notification",
    "statement is ready", "monthly statement", "credit card statement",
    "minimum due", "due date reminder", "auto-pay",
    "account summary", "balance update",
    # Airline frequent-flyer / loyalty
    "miles earned", "miles update", "tier status",
    # E-commerce promos
    "order confirmation", "your order shipped", "delivery update",
    "your order has been", "track your order", "review your purchase",
    # Social-media feed digests
    "see ", " in your feed", "your feed", "see what",
    "what you've missed", "see what's new",
    "the world needs to see", "world needs to see",
    # Generic marketing
    "save up to", "% off", "save big", "introducing", "now available",
    "you're invited to", "register now", "join us for", "early access",
    "limited time", "while supplies last", "ends today", "ends tonight",
    "don't miss", "last chance",
    "jackpot", "final call",
)

# Subject keywords that ALWAYS surface even from junk domains — these are
# things you'd want to know even if they came from no-reply@bank.com.
_SUBJECT_OVERRIDE_PATTERNS = (
    "fraud", "blocked", "suspicious", "otp", "verification code",
    "security alert", "urgent", "action required",
    "password reset", "account compromised",
)


def _is_junk(item: "EmailItem") -> bool:
    """True if the item matches well-known marketing/social patterns that
    we never want in the Brief, no matter how recent/unread.

    Override: subjects matching security-critical patterns (fraud, OTP,
    security alert, password reset) ALWAYS pass through, even from junk
    domains."""
    subj_lower = item.subject.lower()

    if any(p in subj_lower for p in _SUBJECT_OVERRIDE_PATTERNS):
        return False  # security-critical — always surface

    sender_lower = item.sender_email.lower()
    if any(j in sender_lower for j in _JUNK_DOMAINS):
        return True
    if any(p in subj_lower for p in _JUNK_SUBJECT_PATTERNS):
        return True
    return False


@dataclass
class EmailItem:
    account: str
    msg_id: str
    thread_id: str
    sender_name: str
    sender_email: str
    subject: str
    snippet: str
    received_at: datetime.datetime
    labels: list[str]
    score: float = 0.0


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_sender(from_header: str) -> tuple[str, str]:
    name, email = parseaddr(from_header)
    if not name:
        name = email.split("@", 1)[0] if "@" in email else email
    return (name.strip().strip('"'), email.lower())


def _parse_date(date_header: str) -> datetime.datetime:
    try:
        return parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return datetime.datetime.now(datetime.timezone.utc)


def _gmail_url(account_name: str, msg_id: str) -> str:
    """Deep link to open the message in Gmail web, account-correct."""
    email = google.GMAIL_ACCOUNTS.get(account_name, "")
    qs = urllib.parse.urlencode({"authuser": email})
    return f"https://mail.google.com/mail/?{qs}#inbox/{msg_id}"


def _score(item: EmailItem) -> float:
    """Higher = more important. Used to rank across all 4 accounts."""
    s = 0.0
    # Unread bonus
    if "UNREAD" in item.labels:
        s += 10
    # Important / Starred labels
    if "IMPORTANT" in item.labels:
        s += 5
    if "STARRED" in item.labels:
        s += 3
    # Urgency keywords in subject + snippet
    text = (item.subject + " " + item.snippet).lower()
    for kw in _URGENCY_KEYWORDS:
        if kw in text:
            s += 4
            break
    # Recency: emails from the last 6 hours rank higher
    age_h = max(0, (datetime.datetime.now(datetime.timezone.utc) - item.received_at).total_seconds() / 3600)
    s += max(0, 5 - age_h * 0.5)
    return s


def _fetch_account(account: str) -> list[EmailItem]:
    """Pull recent unread emails from one account."""
    # `is:unread newer_than:2d` covers everything fresh worth surfacing.
    qs = urllib.parse.urlencode({
        "q": "is:unread newer_than:2d in:inbox",
        "maxResults": "15",
    })
    try:
        listing = google.bearer_get_json(account, f"{GMAIL_BASE}/messages?{qs}")
    except google.GoogleAuthError as e:
        print(f"[email] {account}: list failed: {e}", file=sys.stderr)
        raise

    items: list[EmailItem] = []
    for ref in listing.get("messages") or []:
        msg_id = ref.get("id")
        if not msg_id:
            continue
        # Lightweight metadata-only fetch.
        meta_qs = "format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        try:
            msg = google.bearer_get_json(
                account, f"{GMAIL_BASE}/messages/{msg_id}?{meta_qs}",
            )
        except google.GoogleAuthError as e:
            print(f"[email] {account}: msg {msg_id} failed: {e}", file=sys.stderr)
            continue
        headers = msg.get("payload", {}).get("headers", []) or []
        sender_name, sender_email = _parse_sender(_header(headers, "From"))
        received_at = _parse_date(_header(headers, "Date"))
        item = EmailItem(
            account=account,
            msg_id=msg_id,
            thread_id=msg.get("threadId") or "",
            sender_name=sender_name or sender_email,
            sender_email=sender_email,
            subject=_header(headers, "Subject").strip() or "(no subject)",
            snippet=msg.get("snippet", "").strip(),
            received_at=received_at,
            labels=msg.get("labelIds") or [],
        )
        item.score = _score(item)
        items.append(item)
    return items


_BAD_WIKILINK = re.compile(r"[\[\]/\\<>:\"|*?]")


def _safe_name(name: str) -> str:
    """Strip characters that would break Obsidian wikilinks or filenames."""
    cleaned = _BAD_WIKILINK.sub("", name).strip()
    if not cleaned:
        return "Unknown Sender"
    return cleaned[:80]


def _format(item: EmailItem) -> str:
    tag = ACCOUNT_TAG.get(item.account, "?")
    name = _safe_name(item.sender_name)
    subj = item.subject.replace("|", "/")
    url = _gmail_url(item.account, item.msg_id)
    return f"- [ ] [{tag}] From [[{name}]] — [{subj}]({url})"


def _render_brief_section(top: list[EmailItem]) -> str:
    if not top:
        return "_Inbox quiet — nothing unread in the last 48h._"
    return "\n".join(_format(item) for item in top)


def _render_triage_overflow(overflow: list[EmailItem]) -> str:
    if not overflow:
        return "Nothing beyond the Brief."
    return "\n".join(_format(item) for item in overflow)


def _write_triage(overflow: list[EmailItem]) -> None:
    """Append the overflow list to today's section of `📥 Email Triage.md`."""
    body = _render_triage_overflow(overflow)
    vault.insert_today_entry(vault.STREAM_NOTES["triage"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["triage"])


def run() -> str:
    """Return the body string for Brief's 'Email' section. Also writes the
    overflow list to `📥 Email Triage.md`."""
    all_items: list[EmailItem] = []
    failures: list[tuple[str, str]] = []
    for account in google.GMAIL_ACCOUNTS:
        try:
            all_items.extend(_fetch_account(account))
        except google.GoogleAuthError as e:
            failures.append((account, str(e)))

    if not all_items and failures:
        body = (
            "> [!warning] All 4 Gmail accounts unreachable\n"
            + "\n".join(f"> - {a}: {e[:120]}" for a, e in failures)
        )
        # Still write the warning to Triage so it surfaces there too.
        vault.insert_today_entry(vault.STREAM_NOTES["triage"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["triage"])
        return body

    # Drop junk before ranking so it never crowds out real mail. Per-account
    # accounting: if an account's entire inbox is junk, skip it silently
    # rather than letting LinkedIn nudges fill the Brief.
    real_items = [it for it in all_items if not _is_junk(it)]
    junk_count = len(all_items) - len(real_items)

    # Sort by score (desc), then by recency (newer first).
    real_items.sort(key=lambda x: (-x.score, -x.received_at.timestamp()))
    top = real_items[:_TOP_N_FOR_BRIEF]
    overflow = real_items[_TOP_N_FOR_BRIEF:]

    _write_triage(overflow)

    body = _render_brief_section(top)
    if junk_count:
        body += f"\n\n_Filtered {junk_count} junk/marketing email{'s' if junk_count != 1 else ''}._"
    if failures:
        body += (
            "\n\n> [!warning] Some accounts unreachable: "
            + ", ".join(a for a, _ in failures)
        )
    return body


def count_per_day(start: datetime.datetime, end_inclusive: datetime.datetime) -> tuple[dict[datetime.date, int], int, list[tuple[str, str]]]:
    """For each day in [start, end_inclusive], count qualifying (non-junk)
    inbox messages. Returns (counts_by_date, total_junk_filtered, failures).

    Used by the weekly recap. One query per account with a date range, then
    bucket the response by Date header day."""
    failures: list[tuple[str, str]] = []
    start_d = start.date()
    end_d = end_inclusive.date()
    # Gmail's after:/before: take YYYY/MM/DD; before: is EXCLUSIVE upper.
    after = start_d.strftime("%Y/%m/%d")
    before = (end_d + datetime.timedelta(days=1)).strftime("%Y/%m/%d")
    qs = urllib.parse.urlencode({
        "q": f"in:inbox after:{after} before:{before}",
        "maxResults": "500",
    })

    counts: dict[datetime.date, int] = {}
    junk_total = 0
    for account in google.GMAIL_ACCOUNTS:
        try:
            listing = google.bearer_get_json(account, f"{GMAIL_BASE}/messages?{qs}")
        except google.GoogleAuthError as e:
            failures.append((account, str(e)))
            continue
        for ref in (listing.get("messages") or []):
            msg_id = ref.get("id")
            if not msg_id:
                continue
            try:
                msg = google.bearer_get_json(
                    account,
                    f"{GMAIL_BASE}/messages/{msg_id}"
                    "?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date",
                )
            except google.GoogleAuthError:
                continue
            headers = msg.get("payload", {}).get("headers", []) or []
            sender_name, sender_email = _parse_sender(_header(headers, "From"))
            received_at = _parse_date(_header(headers, "Date"))
            subject = _header(headers, "Subject").strip() or "(no subject)"
            item = EmailItem(
                account=account, msg_id=msg_id, thread_id="",
                sender_name=sender_name, sender_email=sender_email,
                subject=subject, snippet=msg.get("snippet", "") or "",
                received_at=received_at, labels=msg.get("labelIds") or [],
            )
            if _is_junk(item):
                junk_total += 1
                continue
            day = received_at.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()
            if start_d <= day <= end_d:
                counts[day] = counts.get(day, 0) + 1
    return counts, junk_total, failures


if __name__ == "__main__":
    print(run())
