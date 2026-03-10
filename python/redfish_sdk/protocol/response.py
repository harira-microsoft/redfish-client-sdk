# SPDX-License-Identifier: MIT
# Copyright (c) Microsoft Corporation. All rights reserved.

"""
redfish_sdk/protocol/response.py

RedfishResponse — the uniform return type for every public SDK operation.
Imports: models only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from redfish_sdk.protocol.task import RedfishTask


class RedfishMessage(BaseModel):
    message_id: str = ""
    message: str = ""
    severity: str = "OK"
    resolution: str | None = None
    message_args: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class RedfishResponse(BaseModel):
    status_code: int
    success: bool
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict | list | None = None
    extended_info: list[RedfishMessage] = Field(default_factory=list)
    task: Any | None = None         # RedfishTask | None — Any avoids circular import
    raw: str = ""

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    @model_validator(mode="before")
    @classmethod
    def set_success(cls, values: dict) -> dict:
        if "success" not in values:
            values["success"] = 200 <= values.get("status_code", 0) <= 299
        return values


def build_response(
    status_code: int,
    headers: dict[str, str],
    body_json: dict | list | None,
    body_text: str,
    task: Any | None = None,
) -> RedfishResponse:
    """
    Construct a RedfishResponse from raw HTTP data.
    Parses @Message.ExtendedInfo if present.
    """
    extended_info: list[RedfishMessage] = []

    if isinstance(body_json, dict):
        info = body_json.get("error", {}).get("@Message.ExtendedInfo", [])
        if not info:
            info = body_json.get("@Message.ExtendedInfo", [])
        for entry in info:
            try:
                extended_info.append(RedfishMessage.model_validate(entry))
            except Exception:
                pass

    return RedfishResponse(
        status_code=status_code,
        success=200 <= status_code <= 299,
        headers={k.lower(): v for k, v in headers.items()},
        body=body_json,
        extended_info=extended_info,
        task=task,
        raw=body_text,
    )
