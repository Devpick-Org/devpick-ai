"""AWS Bedrock 공통 유틸리티."""

from __future__ import annotations


def to_tool_config(tool: dict, tool_name: str) -> dict:
    """Anthropic Tool Use 스키마를 Bedrock Converse API toolConfig로 변환한다.

    Anthropic 형식:
        {"name": "...", "description": "...", "input_schema": {...}}

    Bedrock Converse 형식:
        {"tools": [{"toolSpec": {"name": ..., "description": ..., "inputSchema": {"json": {...}}}}],
         "toolChoice": {"tool": {"name": ...}}}
    """
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": {"json": tool["input_schema"]},
                }
            }
        ],
        "toolChoice": {"tool": {"name": tool_name}},
    }
