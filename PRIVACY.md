# Privacy Policy — RiversUnlimited Google Workspace MCP

**Effective date:** August 14, 2026

RiversUnlimited Google Workspace MCP ("the App") is an open-source, **self-hosted** [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI assistants you authorize (such as Claude) work with your Google Workspace data — Gmail, Drive, Docs, Sheets, Slides, Calendar, Forms, Chat, Photos, and Contacts — on your behalf.

Because the App is self-hosted, **your data is processed on infrastructure operated by whoever runs the server instance** (typically you). There is no central service operated by the App's authors, and the App's authors never receive your data.

## What data the App accesses

When you sign in with Google and grant consent, the App requests OAuth scopes to act on the Google services listed above. It accesses only the data needed to carry out actions you (or an AI assistant acting on your instruction) explicitly request — for example reading a spreadsheet range you name, sending an email you compose, or listing calendar events you ask about.

## How data is used

Google user data is used **solely to perform the operations you request** through the MCP interface. It is not used for advertising, profiling, or model training, and it is never sold.

The App's use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the **Limited Use** requirements.

## What is stored, and where

All storage is local to the server instance you run:

- **OAuth credentials** (access and refresh tokens) are stored encrypted at rest in the server's credentials directory so you do not have to re-authenticate on every request.
- **Tool response history** may be cached in a local [Qdrant](https://qdrant.tech) vector database, on the same infrastructure, to power search over past results and usage analytics. Email addresses in this history are redacted or hashed where feasible.
- Nothing is transmitted to the App's authors or to any third party, other than Google's own APIs (and, if the server operator enables them, optional integrations the operator configures — e.g. self-hosted observability).

## Sharing

The App does not sell, rent, or share Google user data with third parties. Data leaves the server only when you direct an action that inherently sends it (e.g. sending an email to a recipient you specify).

## Retention and deletion

Credentials and cached history persist until the server operator deletes them. You can:

- Revoke the App's access at any time from your [Google Account permissions page](https://myaccount.google.com/permissions) — this immediately invalidates its tokens.
- Delete stored credentials and cached data by removing the server's credentials directory and Qdrant collections (or asking the operator of your instance to do so).

## Security

Credentials are encrypted at rest; transport to Google APIs uses TLS. Access to the server is gated by OAuth 2.1, per-user API keys, or an operator-held admin key. The App is open source — its data handling can be audited in full at the repository linked below.

## Children's privacy

The App is not directed at children under 13 and does not knowingly collect data from them.

## Changes

Changes to this policy are published in this repository with the effective date updated above.

## Contact

Questions or requests: open an issue at [github.com/dipseth/google_workspace_fastmcp2](https://github.com/dipseth/google_workspace_fastmcp2/issues) or email **sethrivers@gmail.com**.
