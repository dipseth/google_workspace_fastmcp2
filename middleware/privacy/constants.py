"""Constants for privacy middleware — field patterns and value regexes."""

import re

# Field names whose values should be encrypted when found in tool responses.
# Modeled after _SENSITIVE_RESPONSE_FIELDS in qdrant_middleware.py but focused
# on PII rather than auth tokens.
PRIVACY_FIELD_PATTERNS: frozenset[str] = frozenset(
    {
        # Email-related
        "email",
        "emailAddress",
        "email_address",
        "sender",
        "from",
        "to",
        "cc",
        "bcc",
        "recipient",
        "recipients",
        "replyTo",
        "reply_to",
        "deliveredTo",
        "delivered_to",
        "userEmail",
        # Identity
        "organizer",
        "creator",
        "owner",
        "displayName",
        "display_name",
        "name",
        "fullName",
        "full_name",
        "givenName",
        "familyName",
        "senderName",
        "senderEmail",
        # Contact info
        "phoneNumber",
        "phone_number",
        "phone",
        "address",
    }
)

# Content fields that contain user data but aren't strictly PII identity fields.
# Added to PRIVACY_FIELD_PATTERNS when privacy mode is "auto" with content masking,
# or when the user explicitly includes them via set_privacy_mode(additional_fields=...).
PRIVACY_CONTENT_FIELDS: frozenset[str] = frozenset(
    {
        "snippet",
        "subject",
        "body",
        "text",
        "description",
        "summary",
        "web_url",
        "webUrl",
        "attendees",
        "location",
        "htmlBody",
        "html_body",
        "plainText",
        "plain_text",
        "content",
    }
)

# Regex patterns that detect PII values regardless of field name.
PRIVACY_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
]

# Token format used in masked content.
PRIVATE_TOKEN_PREFIX = "[PRIVATE:"
PRIVATE_TOKEN_SUFFIX = "]"
PRIVATE_TOKEN_PATTERN = re.compile(r"\[PRIVATE:(token_\d+)\]")

# Structured content sentinel keys for encrypted values.
ENCRYPTED_MARKER_KEY = "__private"
ENCRYPTED_CIPHER_KEY = "__enc"
