"""Two-step confirmation helper for destructive MCP tool tests."""

from tools.conftest import _extract_payload_impl


async def confirm_after_preview(session, tool_name, arguments):
    """First call without a valid token (or confirm=False), read confirmation_token
    from structured content, second call with confirm=True and that token.
    Return the second payload dict (not CallToolResult).
    """
    preview_args = {
        key: value for key, value in arguments.items() if key != "confirmation_token"
    }
    preview = _extract_payload_impl(await session.call_tool(tool_name, preview_args))
    token = preview.get("confirmation_token")
    if not token:
        raise AssertionError(
            f"preview payload missing non-empty confirmation_token: {preview!r}"
        )
    confirm_result = await session.call_tool(
        tool_name,
        {**preview_args, "confirm": True, "confirmation_token": token},
    )
    return _extract_payload_impl(confirm_result)
