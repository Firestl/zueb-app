from __future__ import annotations

from typing import Literal, TypedDict


JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject = dict[str, JSONValue]


class SessionData(TypedDict):
    id_token: str
    username: str
    device_id: str


class UserInfo(TypedDict, total=False):
    name: str
    realName: str
    username: str
    mobile: str
    email: str
    orgName: str
    userType: str


class LoginResult(TypedDict):
    id_token: str
    user: UserInfo


class SignatureResult(TypedDict):
    sign: str
    timestamp: int


class SSOCredentials(TypedDict):
    user_code: str
    md5str: str


class AttendanceStatus(TypedDict):
    sbk_time: str
    xbk_time: str
    sbk_done: bool
    xbk_done: bool
    all_done: bool


AttendancePunchMode = Literal["auto", "sbk", "xbk"]
AttendanceResolvedMode = Literal["sbk", "xbk"]


class AttendancePunchResult(TypedDict):
    executed: bool
    mode_requested: AttendancePunchMode
    mode_executed: AttendanceResolvedMode | None
    message: str
    attendance_before: AttendanceStatus
    response: JSONObject | None


class SemesterItem(TypedDict, total=False):
    dm: str
    mc: str
    dqxq: str


class CourseItem(TypedDict, total=False):
    kcmc: str
    skdd: str
    rkjs: str
    jcxx: str
    skzs: str
    xq: str


class PracticalItem(TypedDict, total=False):
    value: str


class ScheduleData(TypedDict, total=False):
    xn: str
    xq: str
    zc: str
    qssj: str
    jssj: str
    maxzc: str
    sjhjinfo: list[PracticalItem]
    week1: list[CourseItem]
    week2: list[CourseItem]
    week3: list[CourseItem]
    week4: list[CourseItem]
    week5: list[CourseItem]
    week6: list[CourseItem]
    week7: list[CourseItem]


class LoginPageConfig(TypedDict, total=False):
    encryptEnabled: bool


class LoginConfigsData(TypedDict, total=False):
    loginPageConfig: LoginPageConfig


class MFAData(TypedDict, total=False):
    mfaEnabled: bool
    need: bool
    state: str


class PasswordLoginData(TypedDict, total=False):
    idToken: str


class _APIResponseBase(TypedDict, total=False):
    code: int
    message: str


class LoginConfigsResponse(_APIResponseBase, total=False):
    data: LoginConfigsData


class MFAResponse(_APIResponseBase, total=False):
    data: MFAData


class PasswordLoginResponse(_APIResponseBase, total=False):
    data: PasswordLoginData


class UserInfoResponse(_APIResponseBase, total=False):
    data: UserInfo


# Card field: [label, "HH:MM"] when punched, or "无" when not.
CardField = list[str] | str


class WebHRCardInfo(TypedDict, total=False):
    sbk: CardField
    xbk: CardField


class WebHRDataEnvelope(TypedDict, total=False):
    data: WebHRCardInfo


class WebHRResponse(TypedDict, total=False):
    data: WebHRDataEnvelope
