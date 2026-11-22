---
title: MCP tools, resources and the stdio transport
type: research-note
status: reviewed
source: https://modelcontextprotocol.io; https://github.com/modelcontextprotocol/python-sdk
accessed: 2026-11-22
author: SegmentationFault
drafted-with: ai, see [[ai-session-2026-11-22-brain-drafts]]
requirements: [FR-5.12, FR-5.13, FR-5.16, CON-8, SE-7]
---

# MCP basics for Cerebra

## Concepts
- A client (the AI app) connects to a server. Messages are JSON-RPC.
- Tools are actions the model may call; resources are readable data; Cerebra exposes six tools
  (FR-5.12) and two resources, quota_status and auth_status (FR-5.13).
- A tool description is read by the model, so create_playlist is labelled as a write operation to let
  clients ask for approval (FR-5.16).

## stdio transport
The client starts the server as a child process and talks over its standard input and output. The
protocol owns stdout, so any stray print there corrupts the stream: log to stderr only. A local
stdio server inherits no network exposure, which is why ADR-E chose it (NFR-SE-7 applies only if an
HTTP transport is ever added).

## Python SDK shape used here
The low-level server registers handlers with decorators for listing tools, calling a tool, listing
resources and reading a resource; the unknown-resource branch returns an error payload and is covered
by a test. Inputs are validated before use (FR-5.14). See [[prompt-injection-defence]] for the trust
model around tool output.
