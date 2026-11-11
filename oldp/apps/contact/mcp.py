"""MCP tool for submitting feedback to the OLDP team.

The agent-facing counterpart of the contact form (:mod:`oldp.apps.contact.views`):
``submit_feedback`` lets an AI agent pass on feature requests, bug reports
and data issues, and emails them to ``SITE_EMAIL`` via Django's email
backend, like the contact form does.

Only signed-in callers (OAuth or API token) may submit, so every message can
be traced to an account and answered. The MCP view answers anonymous calls
with HTTP 401 and an OAuth challenge (``SIGN_IN_REQUIRED_TOOLS`` in
:mod:`oldp.apps.mcp.views`); the check in the tool itself is the fallback
for callers that bypass the view. Submissions are additionally capped per user and
day (``MCP_FEEDBACK_DAILY_LIMIT``, default 10) to keep a looping agent from
flooding the inbox.
"""

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.utils import timezone
from mcp_server import MCPToolset

from oldp.apps.mcp.monitoring import log_tool_call

logger = logging.getLogger("oldp.mcp.tools")

#: Allowed feedback categories -> label used in the email.
FEEDBACK_CATEGORIES = {
    "feature_request": "Feature request",
    "bug_report": "Bug report",
    "data_issue": "Data issue",
    "other": "Other",
}

MESSAGE_MIN_LENGTH = 20
MESSAGE_MAX_LENGTH = 5000
SUBJECT_MAX_LENGTH = 200
CONTEXT_MAX_LENGTH = 2000
_DEFAULT_DAILY_LIMIT = 10

_SUBJECT_TPL = "MCP feedback (%(category)s): %(subject)s"
_MESSAGE_TPL = (
    "Category: %(category)s\n"
    "Subject: %(subject)s\n"
    "User: %(username)s (id %(user_id)s)\n"
    "Email: %(email)s\n"
    "Auth: %(auth)s\n"
    "Client: %(client)s\n"
    "Context:\n%(context)s\n\n"
    "Message:\n\n%(message)s\n"
)


def _signup_url() -> str | None:
    from oldp.api.whoami import _site_url

    return _site_url("account_signup")


class FeedbackTools(MCPToolset):
    """Feedback channel from agents to the OLDP team."""

    @log_tool_call
    def submit_feedback(
        self,
        category: str,
        message: str,
        subject: str = "",
        context: str = "",
    ) -> dict:
        """Send feedback about OLDP or this MCP server to the OLDP team.

        Use this to report bugs (wrong results, errors, broken tools),
        problems with the legal data (missing or wrong decisions, laws or
        references), or to request features. Only submit feedback the user
        wants to send or has agreed to; do not include personal data or
        confidential case details. Requires a signed-in connection (OAuth or
        API token); anonymous calls are answered with HTTP 401 and an OAuth
        challenge, so the client can offer the user to sign in.

        Args:
            category: One of ``feature_request``, ``bug_report``,
                ``data_issue`` or ``other``.
            message: The feedback itself, in English or German
                (20-5000 characters). For bugs, describe what you did, what
                you expected and what happened instead.
            subject: Optional one-line summary (max 200 characters).
            context: Optional technical context (max 2000 characters), e.g.
                the tool name and arguments involved, case IDs, ECLI or law
                references.

        Returns:
            ``{"submitted": true, ...}`` on success, otherwise ``{"error": ...}``.
        """
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return {
                "error": (
                    "Feedback requires a signed-in connection. Connect with "
                    "OAuth (OLDP account) or send an API token, then retry."
                ),
                "signup_url": _signup_url(),
            }

        category = (category or "").strip().lower()
        message = (message or "").strip()
        subject = " ".join((subject or "").split())  # no newlines in headers
        context = (context or "").strip()

        if category not in FEEDBACK_CATEGORIES:
            return {
                "error": "Invalid category.",
                "allowed_categories": list(FEEDBACK_CATEGORIES),
            }
        if not MESSAGE_MIN_LENGTH <= len(message) <= MESSAGE_MAX_LENGTH:
            return {
                "error": (
                    f"message must be {MESSAGE_MIN_LENGTH}-{MESSAGE_MAX_LENGTH} "
                    f"characters long (got {len(message)})."
                )
            }
        if len(subject) > SUBJECT_MAX_LENGTH:
            return {
                "error": f"subject must be at most {SUBJECT_MAX_LENGTH} characters."
            }
        if len(context) > CONTEXT_MAX_LENGTH:
            return {
                "error": f"context must be at most {CONTEXT_MAX_LENGTH} characters."
            }

        limit = getattr(settings, "MCP_FEEDBACK_DAILY_LIMIT", _DEFAULT_DAILY_LIMIT)
        counter_key = f"mcp:feedback:{user.pk}:{timezone.now().date().isoformat()}"
        cache.add(counter_key, 0, timeout=60 * 60 * 24)
        if cache.get(counter_key, 0) >= limit:
            return {
                "error": (
                    f"Daily feedback limit of {limit} submissions reached. "
                    "Please try again tomorrow."
                ),
                "retryable": False,
            }

        email, sent = self._send(user, category, subject, message, context)
        if not sent:
            return {
                "error": "Feedback could not be delivered. Please try again later.",
                "retryable": True,
            }
        try:
            cache.incr(counter_key)
        except ValueError:  # key evicted between add() and incr()
            cache.set(counter_key, 1, timeout=60 * 60 * 24)

        return {
            "submitted": True,
            "category": category,
            "subject": email.subject,
            "message": (
                "Thank you, your feedback was sent to the OLDP team. Replies, "
                "if any, go to the email address of the signed-in account."
            ),
        }

    def _send(self, user, category, subject, message, context):
        """Email the feedback to ``SITE_EMAIL``.

        Returns:
            Tuple of the ``EmailMessage`` and whether sending succeeded.
        """
        auth = getattr(self.request, "auth", None)
        application = getattr(auth, "application", None)
        client = getattr(application, "name", "") or "-"
        auth_method = "oauth" if application is not None else "token/session"
        if not subject:
            first_line = " ".join(message.splitlines()[0].split())
            subject = first_line[:80] + ("…" if len(first_line) > 80 else "")

        values = {
            "category": FEEDBACK_CATEGORIES[category],
            "subject": subject,
            "username": user.get_username(),
            "user_id": user.pk,
            "email": user.email or "-",
            "auth": auth_method,
            "client": client,
            "context": context or "-",
            "message": message,
        }
        email = EmailMessage(
            subject=_SUBJECT_TPL % values,
            body=_MESSAGE_TPL % values,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SITE_EMAIL],
            reply_to=[user.email] if user.email else None,
        )
        try:
            email.send(fail_silently=False)
        except Exception:
            logger.exception("mcp_feedback_send_failed user=%s", user.pk)
            return email, False
        return email, True
