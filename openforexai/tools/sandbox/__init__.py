"""Sandbox-only tools — never wired into a real agent's tool_config.

These tools depend on ``ToolContext.extra["candle_index_map"]``, which is only
populated by the Prompt Workbench's detached-agent execution path
(``POST /prompt-workbench/chat`` in ``openforexai/management/api.py``). Calling
them outside that path returns an error instead of raising, since the map is
simply empty.
"""
