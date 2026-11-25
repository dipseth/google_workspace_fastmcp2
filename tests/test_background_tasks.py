"""The tasks extension is registered with this server's result retention."""

from datetime import timedelta

from fastmcp import FastMCP

from tools import background_tasks
from tools.background_tasks import RESULT_RETENTION, ensure_tasks_extension


def _registered_ttl(monkeypatch) -> timedelta:
    """The ``execution_ttl`` the extension is built with, as Docket will see it."""
    import fastmcp_tasks

    built = []
    real = fastmcp_tasks.TasksExtension

    def recording(**kwargs):
        extension = real(**kwargs)
        built.append(extension)
        return extension

    monkeypatch.setattr(fastmcp_tasks, "TasksExtension", recording)
    assert ensure_tasks_extension(FastMCP("test-server")) is True
    return built[0].docket_settings.execution_ttl


def test_results_are_kept_for_an_hour_by_default(monkeypatch):
    monkeypatch.delenv("FASTMCP_DOCKET_EXECUTION_TTL", raising=False)

    assert RESULT_RETENTION >= timedelta(hours=1)
    assert _registered_ttl(monkeypatch) == RESULT_RETENTION


def test_a_configured_retention_wins(monkeypatch):
    monkeypatch.setenv("FASTMCP_DOCKET_EXECUTION_TTL", "PT3H")

    assert background_tasks._execution_ttl() is None
    assert _registered_ttl(monkeypatch) == timedelta(hours=3)


def test_registering_twice_is_harmless():
    mcp = FastMCP("test-server")

    assert ensure_tasks_extension(mcp) is True
    assert ensure_tasks_extension(mcp) is True
