"""Python orchestrator for the morning briefing workflow.

Stream modules each implement a `run(ctx) -> StreamResult` function. The
top-level runner imports them in dependency order, calls each, writes
outputs to vault files. LLM calls go to llama-server directly via
/v1/chat/completions; data fetches go to public APIs or Google REST APIs
with cached OAuth tokens.
"""
