"""MCP JSON-RPC 2.0 tool call handler.

Routing is handled by MQTTBridge -> SwitchBotDevice.handle_mcp_request().
This module provides tool listing helpers for device introspection.
"""

import logging

logger = logging.getLogger(__name__)


def get_device_tools(device) -> list[dict]:
    """Return OpenAI function-calling compatible tool definitions for a device."""
    tools = []
    for name in device._tools:
        tools.append({
            "name": name,
            "device_id": device.soms_device_id,
            "device_type": device.device_type,
        })
    return tools


def list_all_tools(devices: dict) -> list[dict]:
    """List all MCP tools across all registered devices."""
    all_tools = []
    for device in devices.values():
        all_tools.extend(get_device_tools(device))
    return all_tools
