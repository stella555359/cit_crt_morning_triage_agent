from __future__ import annotations

import html
import re
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .models import EmailAttachmentSummary, EmailLinkCandidate, EmailParseResult


URL_PATTERN = re.compile(r"https?://[^\s<>\")']+", re.IGNORECASE)
HREF_PATTERN = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
TRAILING_URL_CHARS = ".,;:!?)]}>\"'"
DOWNLOAD_KEYWORDS = (
    "download",
    "robot_report.zip",
    ".zip",
    "output.xml",
    "log.html",
    "artifact",
    "artifacts",
    "logs",
)
PORTAL_HOST_KEYWORDS = ("rep-portal", "reporting_portal", "test-reports", "test-report")
JENKINS_HOST_KEYWORDS = ("jenkins", "/job/")
OUTLOOK_SAFELINK_HOST_KEYWORDS = ("safelinks.protection.outlook.com", "eur01.safelinks.protection.outlook.com")


def parse_email_file(path: str | Path, *, sample_chars: int = 500) -> EmailParseResult:
    source_path = Path(path)
    raw_bytes = source_path.read_bytes()

    if source_path.suffix.lower() == ".msg":
        return _parse_msg_best_effort(source_path, raw_bytes, sample_chars=sample_chars)

    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    return _parse_message(source_path, message, sample_chars=sample_chars)


def _parse_message(source_path: Path, message: Message, *, sample_chars: int) -> EmailParseResult:
    body_text = _message_body_text(message)
    links = _extract_link_candidates(body_text)
    attachments = _attachment_summaries(message)

    return EmailParseResult(
        source=str(source_path),
        subject=_string_header(message.get("subject")),
        from_address=_string_header(message.get("from")),
        to_addresses=[address for _, address in getaddresses(message.get_all("to", [])) if address],
        sent_at=_sent_at(message),
        body_text_length=len(body_text),
        body_text_sample=body_text[:sample_chars],
        link_count=len(links),
        download_candidates=[link for link in links if link.category == "download_candidate"],
        portal_links=[link for link in links if link.category == "portal_link"],
        jenkins_links=[link for link in links if link.category == "jenkins_link"],
        all_links=links,
        attachments=attachments,
    )


def _parse_msg_best_effort(source_path: Path, raw_bytes: bytes, *, sample_chars: int) -> EmailParseResult:
    extracted = _parse_msg_with_optional_library(source_path)
    if extracted:
        subject, sender, recipients, sent_at, body_text, attachments = extracted
    else:
        subject = None
        sender = None
        recipients = []
        sent_at = None
        body_text = _decode_best_effort(raw_bytes)
        attachments = []

    links = _extract_link_candidates(body_text)
    return EmailParseResult(
        source=str(source_path),
        subject=subject,
        from_address=sender,
        to_addresses=recipients,
        sent_at=sent_at,
        body_text_length=len(body_text),
        body_text_sample=body_text[:sample_chars],
        link_count=len(links),
        download_candidates=[link for link in links if link.category == "download_candidate"],
        portal_links=[link for link in links if link.category == "portal_link"],
        jenkins_links=[link for link in links if link.category == "jenkins_link"],
        all_links=links,
        attachments=attachments,
    )


def _parse_msg_with_optional_library(
    source_path: Path,
) -> tuple[str | None, str | None, list[str], str | None, str, list[EmailAttachmentSummary]] | None:
    try:
        import extract_msg  # type: ignore[import-not-found]
    except ImportError:
        return None

    msg = extract_msg.Message(str(source_path))
    plain_body = str(getattr(msg, "body", "") or "")
    html_body = str(getattr(msg, "htmlBody", "") or "")
    html_href_text = "\n".join(HREF_PATTERN.findall(html_body))
    body_text = "\n\n".join(part for part in [plain_body, html_href_text, _html_to_text(html_body)] if part)
    recipients = [recipient.email for recipient in getattr(msg, "recipients", []) if getattr(recipient, "email", None)]
    attachments = [
        EmailAttachmentSummary(
            filename=getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", None),
            content_type=getattr(attachment, "mimetype", None),
            size_bytes=len(getattr(attachment, "data", b"") or b""),
        )
        for attachment in getattr(msg, "attachments", [])
    ]
    sent_at = str(getattr(msg, "date", "")) or None
    return getattr(msg, "subject", None), getattr(msg, "sender", None), recipients, sent_at, body_text, attachments


def _message_body_text(message: Message) -> str:
    text_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            content_disposition = str(part.get_content_disposition() or "").lower()
            if content_disposition == "attachment":
                continue
            _collect_body_part(part, text_parts=text_parts, html_parts=html_parts)
    else:
        _collect_body_part(message, text_parts=text_parts, html_parts=html_parts)

    html_href_text = "\n".join(href for value in html_parts for href in HREF_PATTERN.findall(value))
    html_text = [_html_to_text(value) for value in html_parts]
    return "\n\n".join(part for part in text_parts + [html_href_text] + html_text if part)


def _collect_body_part(part: Message, *, text_parts: list[str], html_parts: list[str]) -> None:
    content_type = part.get_content_type().lower()
    if content_type not in {"text/plain", "text/html"}:
        return

    try:
        content = part.get_content() if isinstance(part, EmailMessage) else part.get_payload(decode=True)
    except Exception:
        content = None

    if isinstance(content, bytes):
        charset = part.get_content_charset() or "utf-8"
        content = content.decode(charset, errors="ignore")
    if content is None:
        return

    if content_type == "text/html":
        html_parts.append(str(content))
    else:
        text_parts.append(str(content))


def _attachment_summaries(message: Message) -> list[EmailAttachmentSummary]:
    attachments: list[EmailAttachmentSummary] = []
    for part in message.walk() if message.is_multipart() else []:
        if str(part.get_content_disposition() or "").lower() != "attachment":
            continue
        payload = part.get_payload(decode=True)
        attachments.append(
            EmailAttachmentSummary(
                filename=part.get_filename(),
                content_type=part.get_content_type(),
                size_bytes=len(payload) if payload is not None else None,
            )
        )
    return attachments


def _extract_link_candidates(text: str) -> list[EmailLinkCandidate]:
    raw_urls = HREF_PATTERN.findall(text) + URL_PATTERN.findall(text)
    candidates: list[EmailLinkCandidate] = []
    seen: set[str] = set()

    for raw_url in raw_urls:
        original_url = _clean_url(raw_url)
        normalized_url = _normalize_url(original_url)
        if not normalized_url or normalized_url in seen:
            continue
        seen.add(normalized_url)
        category, reason = _categorize_url(normalized_url)
        candidates.append(
            EmailLinkCandidate(
                original_url=original_url,
                normalized_url=normalized_url,
                category=category,
                reason=reason,
            )
        )

    return candidates


def _clean_url(value: str) -> str:
    cleaned = html.unescape(value.strip()).rstrip(TRAILING_URL_CHARS)
    return cleaned.replace("\\u0026", "&")


def _normalize_url(value: str) -> str:
    parsed = urlparse(value)
    if any(keyword in parsed.netloc.lower() for keyword in OUTLOOK_SAFELINK_HOST_KEYWORDS):
        wrapped_url = parse_qs(parsed.query).get("url", [None])[0]
        if wrapped_url:
            return _clean_url(unquote(wrapped_url))
    return value


def _categorize_url(url: str) -> tuple[str, str]:
    normalized = url.lower()
    if any(keyword in normalized for keyword in DOWNLOAD_KEYWORDS):
        return "download_candidate", "URL contains a report/log download keyword."
    if any(keyword in normalized for keyword in PORTAL_HOST_KEYWORDS):
        return "portal_link", "URL points to Reporting Portal or a test report page."
    if any(keyword in normalized for keyword in JENKINS_HOST_KEYWORDS):
        return "jenkins_link", "URL points to Jenkins."
    return "other_link", "URL does not match the first-pass report source rules."


def _html_to_text(value: str) -> str:
    without_tags = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    without_tags = re.sub(r"(?i)<br\s*/?>", "\n", without_tags)
    without_tags = re.sub(r"(?i)</p\s*>", "\n", without_tags)
    without_tags = re.sub(r"(?is)<[^>]+>", " ", without_tags)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", without_tags))


def _decode_best_effort(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16-le", "latin-1"):
        try:
            decoded = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "http" in decoded.lower():
            return decoded
    return raw_bytes.decode("latin-1", errors="ignore")


def _string_header(value: object) -> str | None:
    return str(value) if value is not None else None


def _sent_at(message: Message) -> str | None:
    raw_date = message.get("date")
    if not raw_date:
        return None
    try:
        return parsedate_to_datetime(str(raw_date)).isoformat()
    except Exception:
        return str(raw_date)
