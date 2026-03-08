from __future__ import annotations

from cli.types import CardField, JSONObject, WebHRCardInfo, WebHRDataEnvelope, WebHRResponse


def _expect_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return value


def _parse_card_field(value: object, *, context: str) -> CardField:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a string or string list")

    card_field: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{context}[{index}] must be a string")
        card_field.append(item)
    return card_field


def parse_webhr_token_response(payload: object) -> str:
    source = _expect_object(payload, "appLoginsso response")
    outer = _expect_object(source.get("data"), "appLoginsso response.data")
    inner = _expect_object(outer.get("data"), "appLoginsso response.data.data")

    token = inner.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("appLoginsso response.data.data.token must be a non-empty string")
    return token


def parse_webhr_card_info_response(payload: object) -> WebHRResponse:
    source = _expect_object(payload, "getKqCardInfo response")
    outer = _expect_object(source.get("data"), "getKqCardInfo response.data")
    inner = _expect_object(outer.get("data"), "getKqCardInfo response.data.data")

    card_info: WebHRCardInfo = {}
    if "sbk" in inner:
        card_info["sbk"] = _parse_card_field(
            inner["sbk"],
            context="getKqCardInfo response.data.data.sbk",
        )
    if "xbk" in inner:
        card_info["xbk"] = _parse_card_field(
            inner["xbk"],
            context="getKqCardInfo response.data.data.xbk",
        )

    envelope: WebHRDataEnvelope = {"data": card_info}
    return {"data": envelope}


def parse_webhr_save_response(payload: object) -> JSONObject:
    source = _expect_object(payload, "saveKqCard response")
    return {str(key): value for key, value in source.items()}
