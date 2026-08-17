"""
Tests for the search_people tool (name -> person/email resolution).

search_people is the demonstrable feature behind the contacts and
directory.readonly scopes: it searches saved contacts via
people.searchContacts and the Workspace org directory via
people.searchDirectoryPeople, skipping the directory gracefully on
consumer accounts (which have none).

These tests mock the People API service, so they run in every environment.
"""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from people.people_tools import search_people

CONTACT = {
    "resourceName": "people/c1",
    "names": [{"displayName": "Dan Edelstein"}],
    "emailAddresses": [{"value": "dedelste88@gmail.com"}],
}
DIRECTORY_PERSON = {
    "resourceName": "people/d1",
    "names": [{"displayName": "Dana Rivers"}],
    "emailAddresses": [{"value": "dana@riversunlimited.xyz"}],
    "organizations": [{"title": "Engineer", "name": "Rivers Unlimited"}],
}


def _http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "error"
    return HttpError(resp=resp, content=b"error")


@pytest.fixture
def people_service():
    service = MagicMock()
    with patch("people.people_tools._get_people_service", return_value=service):
        yield service


async def test_resolves_name_to_contact_email(people_service):
    people_service.people().searchContacts().execute.return_value = {
        "results": [{"person": CONTACT}]
    }
    people_service.people().searchDirectoryPeople().execute.side_effect = _http_error(
        403
    )

    result = await search_people("Dan", user_google_email="user@example.com")

    assert result.success is True
    assert result.total_count == 1
    match = result.results[0]
    assert match.display_name == "Dan Edelstein"
    assert match.emails == ["dedelste88@gmail.com"]
    assert match.source == "contacts"


async def test_directory_results_merge_on_workspace_accounts(people_service):
    people_service.people().searchContacts().execute.return_value = {"results": []}
    people_service.people().searchDirectoryPeople().execute.return_value = {
        "people": [DIRECTORY_PERSON]
    }

    result = await search_people("Dana", user_google_email="user@example.com")

    assert result.success is True
    assert result.directory_searched is True
    assert result.directory_note is None
    match = result.results[0]
    assert match.source == "directory"
    assert match.emails == ["dana@riversunlimited.xyz"]
    assert match.organizations == ["Engineer @ Rivers Unlimited"]


async def test_consumer_account_skips_directory_gracefully(people_service):
    people_service.people().searchContacts().execute.return_value = {
        "results": [{"person": CONTACT}]
    }
    people_service.people().searchDirectoryPeople().execute.side_effect = _http_error(
        403
    )

    result = await search_people("Dan", user_google_email="user@example.com")

    assert result.success is True
    assert result.directory_searched is False
    assert "consumer" in (result.directory_note or "").lower()
    assert result.total_count == 1


async def test_contacts_failure_reports_error(people_service):
    people_service.people().searchContacts().execute.side_effect = _http_error(500)

    result = await search_people("Dan", user_google_email="user@example.com")

    assert result.success is False
    assert result.error is not None
