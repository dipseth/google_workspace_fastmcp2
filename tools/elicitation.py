"""Asking the connected client for input without losing the tool call.

MCP elicitation lets a tool pause and put a question to the user: a form to
fill in (``mode: "form"``) or a URL to visit (``mode: "url"``, the fit for
OAuth). How the question is delivered depends on the protocol era the
connection negotiated, and the two shapes are not interchangeable:

* **Handshake era** (2025-11-25, 2025-06-18, …) — the server pushes
  ``elicitation/create`` over the back-channel and awaits the answer inside the
  same tool call (``ctx.elicit`` for forms, ``session.elicit_url`` for URLs).
* **2026-07-28** — SEP-2577 removed the back-channel, so nothing can be pushed.
  The tool instead *returns* an ``InputRequiredResult`` carrying the request
  (SEP-2322, the guard-tool pattern); the client collects the answer and calls
  the tool again with the original arguments plus ``inputResponses``. On that
  re-run :func:`answered_prompt` reports what the user did.

One call per question type hides the split:

* :func:`prompt_for_form` — a form under a stable key. ``suspended`` with the
  result to hand back on 2026-07-28; ``unsupported`` otherwise, so the caller
  keeps its ``ctx.elicit`` push or its own fallback.
* :func:`prompt_for_oauth` — send the user to an authorization URL. Handles
  both eras itself: ``completed``/``declined`` when a handshake-era push was
  answered inline, ``suspended`` on 2026-07-28, and a form carrying the link
  for clients that only declare form mode.

A call that runs as a **background task** (SEP-2663) asks the same way — the
returned ``InputRequiredResult`` parks the task in ``input_required`` until the
client answers with ``tasks/update`` — but its worker has no session to read
the client's capabilities from, and a tool it runs in-process has no request to
read the answers from. Two halves bridge that: :func:`remember_task_client`
notes, on the foreground leg, what the client can be asked, and
:func:`task_leg` hands that note and the leg's answers to everything the worker
runs.

Every failure mode collapses to ``unsupported``, which means "fall back to what
the caller did before". A client that never advertised the mode, a
pre-2025-11-25 connection, no live session (unit test, a task whose client was
never noted), or an unexpected wire error all land there, so this module can
only ever upgrade the experience — it cannot take the existing one away.
``start_google_auth`` and the Gmail send/forward confirmation are the current
callers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterator, Literal, Optional

from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

#: Key the OAuth exchange travels under in ``inputRequests``/``inputResponses``.
#: The client echoes it verbatim, so it must stay stable across both rounds.
OAUTH_INPUT_KEY = "google_oauth"

#: How long to hold a handshake-era tool call open while the user is off at
#: Google. Consent with an account picker and a scope screen is a minutes-long
#: errand, so this is generous — but it is bounded, because a client that never
#: answers would otherwise pin the call open forever. A timeout is not a
#: failure: the caller still gets the clickable link.
ELICIT_TIMEOUT_SECONDS = 300.0

#: Set while a tool is running inside a caller that cannot deliver a suspend
#: result to the client. `InputRequiredToolResult` carries no content, so such
#: a caller would receive an empty value and the authorization URL would simply
#: vanish; suppressing the prompt returns it to the clickable-link response,
#: which survives the trip. Code Mode's ``execute`` used to be that caller; it
#: now propagates the ask as its own result instead, so this is kept for any
#: nested path that still cannot.
_suppressed: ContextVar[bool] = ContextVar("elicitation_suppressed", default=False)


@contextmanager
def suppress_elicitation() -> Iterator[None]:
    """Mark everything run inside as a nested, client-unreachable call."""
    token = _suppressed.set(True)
    try:
        yield
    finally:
        _suppressed.reset(token)


#: Session-state key the foreground leg writes and the worker reads. FastMCP
#: restores the submitting request's session id inside a worker, so state under
#: it is the one channel from the request that created a task to the legs that
#: run it.
TASK_CLIENT_STATE_KEY = "elicitation_task_client"


@dataclass(frozen=True)
class TaskLeg:
    """What one leg of a background task knows that its tools cannot read.

    ``form``/``url`` are the elicitation modes the submitting client declared;
    ``input_responses`` are the answers this leg was re-entered with (None on
    the first leg).
    """

    form: bool = False
    url: bool = False
    input_responses: Any = None


_task_leg: ContextVar[Optional[TaskLeg]] = ContextVar(
    "elicitation_task_leg", default=None
)


async def remember_task_client(ctx: Any, tool_name: str) -> None:
    """Note what the client can be asked, when ``tool_name`` may run as a task.

    Runs on the foreground leg, the only place the client's capabilities are
    readable. Nothing is written unless the call can actually become a task
    that asks: the request opted into the tasks extension, the tool is
    task-capable, and the client declared an elicitation mode. Bookkeeping
    only — a failure here never reaches the request, it just leaves the task
    with today's fallback.
    """
    try:
        from fastmcp.utilities.tasks import TASKS_EXTENSION_ID

        if ctx is None or ctx.client_extension_settings(TASKS_EXTENSION_ID) is None:
            return
        tool = await ctx.fastmcp.get_tool(tool_name)
        if tool is None or not tool.task_config.supports_tasks():
            return
        form = form_elicitation_supported(ctx)
        url = url_elicitation_supported(ctx)
        if form or url:
            await ctx.set_state(TASK_CLIENT_STATE_KEY, {"form": form, "url": url})
    except Exception as exc:
        logger.debug(f"Could not note the task client for '{tool_name}': {exc}")


class TaskClientMiddleware(Middleware):
    """Calls :func:`remember_task_client` ahead of every ``tools/call``.

    Middleware wraps the tasks extension's interceptor, so this runs in the
    request that submits a task and never in the worker that executes it.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        await remember_task_client(
            context.fastmcp_context, getattr(context.message, "name", "")
        )
        return await call_next(context)


@asynccontextmanager
async def task_leg(ctx: Any) -> AsyncIterator[None]:
    """Make this task leg's client and answers visible to the tools it runs.

    A tool body that runs other tools in-process (Code Mode's ``execute``)
    wraps that work in this. Outside a background task it does nothing, so the
    caller need not check where it is running.
    """
    if ctx is None or not getattr(ctx, "is_background_task", False):
        yield
        return
    client: dict[str, Any] = {}
    try:
        client = await ctx.get_state(TASK_CLIENT_STATE_KEY) or {}
    except Exception as exc:
        logger.debug(f"Could not read the task client: {exc}")
    token = _task_leg.set(
        TaskLeg(
            form=bool(client.get("form")),
            url=bool(client.get("url")),
            input_responses=ctx.input_responses,
        )
    )
    try:
        yield
    finally:
        _task_leg.reset(token)


Outcome = Literal["completed", "declined", "suspended", "unsupported"]


@dataclass(frozen=True)
class ElicitationPrompt:
    """What came of asking the user.

    ``outcome`` is ``completed``/``declined`` when a handshake-era push was
    answered inline (``action`` carries the raw answer), ``suspended`` when the
    ask must be returned to the client, and ``unsupported`` when it could not
    be made at all. ``suspend`` is set only for ``suspended`` and is the
    ``InputRequiredResult`` the tool must return unchanged — FastMCP recognizes
    it as a suspend signal rather than output data, provided the tool's return
    annotation includes ``InputRequiredResult``.
    """

    outcome: Outcome
    suspend: Any = None
    action: Optional[str] = None

    @property
    def handled(self) -> bool:
        """True when the caller must not fall back to the link response."""
        return self.outcome in ("completed", "suspended")


def _context() -> Any:
    """The live FastMCP context, or None outside a request."""
    try:
        from fastmcp.server.dependencies import get_context

        return get_context()
    except Exception:
        return None


def _is_modern(ctx: Any) -> bool:
    """True when the connection negotiated an era without a back-channel."""
    if _task_leg.get() is not None:
        # Tasks are only ever created on a 2026-07-28 connection.
        return True
    try:
        from mcp_types.version import MODERN_PROTOCOL_VERSIONS

        return ctx.session.protocol_version in MODERN_PROTOCOL_VERSIONS
    except Exception:
        return False


def _elicitation_capability(ctx: Any) -> Any:
    """The client's declared ``elicitation`` capability, or None."""
    try:
        return getattr(ctx.session.client_capabilities, "elicitation", None)
    except Exception:
        return None


def url_elicitation_supported(ctx: Any = None) -> bool:
    """True when the client declared url-mode elicitation *explicitly*.

    This mirrors the client SDKs' own reading of the capability. A bare
    ``elicitation: {}`` is the pre-2025-11-25 declaration and means form mode
    only: the MCP TypeScript SDK inside Claude Code refuses a url-mode request
    against it with "Client does not support URL-mode elicitation requests",
    thrown client-side before any dialog opens — even though Claude Code's
    dialog could draw one. So url mode needs the ``url`` sub-key, and a
    form-only client is served by :func:`form_elicitation_supported` instead.
    """
    leg = _task_leg.get()
    if leg is not None:
        return leg.url
    ctx = ctx or _context()
    if ctx is None:
        return False
    return getattr(_elicitation_capability(ctx), "url", None) is not None


def form_elicitation_supported(ctx: Any = None) -> bool:
    """True when the client can take a form-mode elicitation.

    An explicit ``form`` sub-key, or the bare declaration — which is what
    Claude Code sends, unconditionally.
    """
    leg = _task_leg.get()
    if leg is not None:
        return leg.form
    ctx = ctx or _context()
    if ctx is None:
        return False
    elicitation = _elicitation_capability(ctx)
    if elicitation is None:
        return False
    return (
        getattr(elicitation, "form", None) is not None
        or getattr(elicitation, "url", None) is None
    )


def answered_prompt(key: str, ctx: Any = None) -> Optional[Any]:
    """The user's answer to an earlier prompt under ``key``, on a re-run.

    None on the first run. Otherwise the raw ``ElicitResult``: ``action`` is
    ``accept``/``decline``/``cancel`` and, for a form prompt that was accepted,
    ``content`` holds the fields the user filled in.
    """
    leg = _task_leg.get()
    if leg is not None:
        responses = leg.input_responses
    else:
        ctx = ctx or _context()
        try:
            responses = ctx.input_responses if ctx is not None else None
        except Exception:
            responses = None
    if not responses:
        return None
    return responses.get(key)


def answered_oauth_prompt(ctx: Any = None) -> Optional[Any]:
    """The user's answer to an earlier OAuth prompt, on a re-run; None on the first.

    Returns the raw ``ElicitResult`` so the caller can distinguish ``accept``
    (they say they finished — verify the credential, never trust the claim)
    from ``decline``/``cancel`` (they backed out).
    """
    return answered_prompt(OAUTH_INPUT_KEY, ctx)


def prompt_for_form(
    key: str,
    message: str,
    schema: dict[str, Any],
    *,
    request_state: Optional[str] = None,
) -> ElicitationPrompt:
    """Ask the user to fill in ``schema`` on a connection without a back-channel.

    Only the 2026-07-28 shape lives here: a form-mode ``InputRequiredResult``
    under ``key`` that the client answers by calling the tool again, where
    :func:`answered_prompt` picks the answer up. Callers return
    ``prompt.suspend`` verbatim on ``suspended``. Everything else comes back
    ``unsupported`` — handshake-era clients should then use ``ctx.elicit``
    (the push form), and clients with no usable form support get the caller's
    own fallback.
    """
    if _suppressed.get():
        logger.info("Form prompt: nested tool call (Code Mode) — unsupported")
        return ElicitationPrompt("unsupported")
    ctx = _context()
    if ctx is None:
        return ElicitationPrompt("unsupported")
    if not (_is_modern(ctx) and form_elicitation_supported(ctx)):
        return ElicitationPrompt("unsupported")
    logger.info(
        f"Form prompt '{key}': 2026-07-28 client — returning InputRequiredResult"
    )
    return _suspend_form_request(key, message, schema, request_state)


async def prompt_for_oauth(
    message: str,
    url: str,
    *,
    request_state: Optional[str] = None,
) -> ElicitationPrompt:
    """Ask the user to complete OAuth at ``url``.

    Args:
        message: Why the user is being sent away, in their own terms.
        url: The authorization URL to open.
        request_state: Small opaque string handed back on the re-run via
            ``ctx.request_state``. The SDK seals it with an authenticated
            cipher, so a client cannot read or forge it — but the default key
            is ephemeral, so a server restart mid-flow invalidates it. Carry
            hints, never anything the re-run cannot rebuild from its arguments.

    Returns:
        An :class:`ElicitationPrompt`. Callers must return ``prompt.suspend`` to the
        client untouched when the outcome is ``suspended``.
    """
    if _suppressed.get():
        logger.info("OAuth prompt: nested tool call (Code Mode) — using the link")
        return ElicitationPrompt("unsupported")

    ctx = _context()
    if ctx is None:
        return ElicitationPrompt("unsupported")

    elicitation_id = str(uuid.uuid4())

    if not url_elicitation_supported(ctx):
        # A form-only client can still be asked without losing the tool call:
        # the form carries the link in its message, and the user confirms once
        # Google is done. Only on 2026-07-28, where the ask is a returned
        # result; a handshake-era form push is a different interaction and
        # untested, so that era keeps the link.
        if form_elicitation_supported(ctx) and _is_modern(ctx):
            logger.info(
                "OAuth prompt: form-only 2026-07-28 client — returning a form "
                "InputRequiredResult carrying the link"
            )
            return _suspend_form(message, url, request_state)
        logger.info(
            "OAuth prompt: client declares no usable elicitation mode — using the link"
        )
        return ElicitationPrompt("unsupported")

    if _is_modern(ctx):
        logger.info("OAuth prompt: 2026-07-28 client — returning InputRequiredResult")
        return _suspend(message, url, elicitation_id, request_state)

    try:
        result = await asyncio.wait_for(
            ctx.session.elicit_url(
                message=message,
                url=url,
                elicitation_id=elicitation_id,
                related_request_id=getattr(ctx, "request_id", None),
            ),
            timeout=ELICIT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.info(
            f"URL elicitation unanswered after {ELICIT_TIMEOUT_SECONDS:.0f}s "
            f"— falling back to the link response"
        )
        return ElicitationPrompt("unsupported")
    except Exception as exc:
        # A back-channel that refuses the push is indistinguishable, from here,
        # from a client that cannot do it at all — both mean "use the link".
        logger.info(f"URL elicitation unavailable ({type(exc).__name__}: {exc})")
        return ElicitationPrompt("unsupported")

    action = getattr(result, "action", None)
    if action == "accept":
        return ElicitationPrompt("completed", action=action)
    return ElicitationPrompt("declined", action=action)


def _suspend(
    message: str,
    url: str,
    elicitation_id: str,
    request_state: Optional[str],
) -> ElicitationPrompt:
    """Build the 2026-07-28 ``InputRequiredResult`` for this prompt."""
    try:
        import mcp_types

        suspend = mcp_types.InputRequiredResult(
            resultType="input_required",
            inputRequests={
                OAUTH_INPUT_KEY: mcp_types.ElicitRequest(
                    method="elicitation/create",
                    params=mcp_types.ElicitRequestURLParams(
                        mode="url",
                        message=message,
                        url=url,
                        elicitationId=elicitation_id,
                    ),
                )
            },
            requestState=request_state,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Could not build OAuth InputRequiredResult: {exc}")
        return ElicitationPrompt("unsupported")
    return ElicitationPrompt("suspended", suspend=suspend)


#: What a form-only client is asked. The link travels in the message — a form
#: field cannot be a hyperlink — and the single boolean is the user's
#: confirmation; the tool verifies the credential regardless of the answer.
OAUTH_FORM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "authorized": {
            "type": "boolean",
            "title": "I have finished authorizing with Google",
            "description": "Confirm once Google has shown its success page.",
            "default": True,
        }
    },
    "required": ["authorized"],
}


def _form_message(message: str, url: str) -> str:
    return (
        f"{message}\n\n"
        f"Open this link to authorize with Google:\n{url}\n\n"
        "When Google shows its success page, come back here and confirm."
    )


def _suspend_form(
    message: str,
    url: str,
    request_state: Optional[str],
) -> ElicitationPrompt:
    """Build the OAuth prompt as a form-mode ``InputRequiredResult``."""
    return _suspend_form_request(
        OAUTH_INPUT_KEY, _form_message(message, url), OAUTH_FORM_SCHEMA, request_state
    )


def _suspend_form_request(
    key: str,
    message: str,
    schema: dict[str, Any],
    request_state: Optional[str],
) -> ElicitationPrompt:
    """Build a 2026-07-28 form-mode ``InputRequiredResult`` under ``key``."""
    try:
        import mcp_types

        suspend = mcp_types.InputRequiredResult(
            resultType="input_required",
            inputRequests={
                key: mcp_types.ElicitRequest(
                    method="elicitation/create",
                    params=mcp_types.ElicitRequestFormParams(
                        mode="form",
                        message=message,
                        requestedSchema=schema,
                    ),
                )
            },
            requestState=request_state,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Could not build form InputRequiredResult '{key}': {exc}")
        return ElicitationPrompt("unsupported")
    return ElicitationPrompt("suspended", suspend=suspend)
