"""
IIIT Mess Management System MCP Server (v2)

Built from the official OpenAPI spec at mess.iiit.ac.in/api/docs.
Requires IIIT VPN to reach the server.

Authentication:
  - MSIT/Intern users: call mess_login_msit → returns a session cookie string
  - All authenticated tools accept either:
      auth_key  = an API key (sent as Authorization header)
      session   = a session cookie string from mess_login_msit
  - IIIT students: CAS login is a browser redirect and CANNOT be done
    programmatically. Log in via the browser, copy your session cookie, and
    pass it as the `session` parameter in tool calls.
  - Set env var MESS_AUTH_KEY to avoid passing auth_key on every call.
"""

import json
import os
from typing import Optional
from enum import Enum

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict, field_validator

#import load env
from dotenv import load_dotenv
# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
BASE_URL = "https://mess.iiit.ac.in/api"
TIMEOUT = 15.0

mcp = FastMCP("mess_mcp")
load_dotenv()


# ─────────────────────────────────────────────
# Auth & HTTP helpers
# ─────────────────────────────────────────────

def _headers(auth_key: Optional[str] = None, session: Optional[str] = None) -> dict:
    h: dict = {}
    key = auth_key or os.environ.get("MESS_AUTH_KEY")
    if key:
        h["Authorization"] = key
    if session and not key:
        h["Cookie"] = f"session={session}"
    return h


async def _req(
    method: str,
    path: str,
    *,
    auth_key: Optional[str] = None,
    session: Optional[str] = None,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
) -> dict:
    clean_params = {k: v for k, v in (params or {}).items() if v is not None} or None
    clean_body = {k: v for k, v in (body or {}).items() if v is not None} or None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.request(
            method=method,
            url=f"{BASE_URL}{path}",
            headers=_headers(auth_key, session),
            params=clean_params,
            json=clean_body,
        )
        try:
            resp.raise_for_status()
            return resp.json() if resp.content else {"status": resp.status_code, "ok": True}
        except httpx.HTTPStatusError as e:
            try:
                return {"http_error": e.response.status_code, "detail": e.response.json()}
            except Exception:
                return {"http_error": e.response.status_code, "detail": e.response.text}


def _out(data: dict) -> str:
    return json.dumps(data, indent=2, default=str)


# ─────────────────────────────────────────────
# Shared Enums & Base Models
# ─────────────────────────────────────────────

class Meal(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    snacks = "snacks"
    dinner = "dinner"


cfg = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AuthInput(BaseModel):
    model_config = cfg
    auth_key: Optional[str] = Field(
        default=None,
        description="API key (from mess_create_auth_key). Can also be set via MESS_AUTH_KEY env var."
    )
    session: Optional[str] = Field(
        default=None,
        description="Session cookie value from mess_login_msit or copied from browser."
    )


# ─────────────────────────────────────────────
# Input Models
# ─────────────────────────────────────────────

class MsitLoginInput(BaseModel):
    model_config = cfg
    user: str = Field(..., description="MSIT student/intern email, e.g. you@msitprogram.net")
    password: str = Field(..., description="Password in plaintext")


class CreateAuthKeyInput(AuthInput):
    name: str = Field(..., description="Unique friendly name for the key")
    expiry: str = Field(..., description="Expiry date YYYY-MM-DD, e.g. '2026-12-31'")


class AuthKeyNameInput(AuthInput):
    name: str = Field(..., description="The name of the auth key (not the key value)")


class ResetPassInput(BaseModel):
    model_config = cfg
    email: str = Field(..., description="Registered MSIT/intern email address")


class ResetPassVerifyInput(BaseModel):
    model_config = cfg
    email: str = Field(..., description="Registered email address")
    otp: str = Field(..., description="6-digit OTP received by email, e.g. '123456'")
    password: str = Field(..., description="New password to set")


class MessMenuInput(BaseModel):
    model_config = cfg
    on: Optional[str] = Field(
        default=None,
        description=(
            "Date YYYY-MM-DD. Defaults to today. "
            "Menus are stored week-wise (week starts Sunday). "
            "Anchor on Sundays for weekly/monthly views."
        )
    )


# class MessMealDateInput(BaseModel):
#     model_config = cfg
#     meal: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")
#     on: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")

class MessMealDateInput(BaseModel):
    model_config = cfg
    meal: str = Field(..., description="Meal: breakfast, lunch, snacks, or dinner. One of: breakfast, lunch, snacks, dinner")
    on: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")

    @field_validator("meal")
    @classmethod
    def validate_meal(cls, v: str) -> str:
        valid = {"breakfast", "lunch", "snacks", "dinner"}
        if v not in valid:
            raise ValueError(f"meal must be one of {valid}")
        return v


class GetRegistrationsInput(AuthInput):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", populate_by_name=True)
    from_date: str = Field(..., alias="from", description="Start date YYYY-MM-DD (inclusive)")
    to_date: str = Field(..., alias="to", description="End date YYYY-MM-DD (inclusive, max 2-month range)")


class CreateRegistrationInput(AuthInput):
    meal_date: str = Field(..., description="Date YYYY-MM-DD")
    meal_type: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")
    meal_mess: str = Field(..., description="Mess ID, e.g. 'kadamba-nonveg', 'yuktahar'")
    guests: Optional[int] = Field(default=None, ge=0, description="Number of guests to bring (optional)")


class GetOneRegistrationInput(AuthInput):
    meal: Optional[Meal] = Field(default=None, description="Meal name. If omitted, returns all meals for the date.")
    date: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")


class SkipMealInput(AuthInput):
    meal_date: str = Field(..., description="Date YYYY-MM-DD")
    meal_type: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")
    meal_mess: str = Field(..., description="Mess ID, e.g. 'kadamba-nonveg'")
    skipping: bool = Field(..., description="True to skip, False to unskip")


class MealDateTypeInput(AuthInput):
    meal_date: str = Field(..., description="Date YYYY-MM-DD")
    meal_type: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")


class FeedbackInput(AuthInput):
    meal_date: str = Field(..., description="Date YYYY-MM-DD")
    meal_type: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")
    rating: int = Field(..., ge=1, le=5, description="Rating 1 (worst) to 5 (best)")
    remarks: Optional[str] = Field(default=None, description="Optional text feedback")


class MealRatingInput(AuthInput):
    meal: Meal = Field(..., description="Meal name")
    mess: Optional[str] = Field(default=None, description="Mess ID. If omitted, returns all messes.")
    date: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")


class MonthYearInput(AuthInput):
    month: Optional[int] = Field(default=None, ge=1, le=12, description="Month 1-12. Defaults to current.")
    year: Optional[int] = Field(default=None, ge=2000, le=2098, description="Year. Defaults to current.")


class CreateMonthlyRegInput(AuthInput):
    month: int = Field(..., ge=1, le=12, description="Month 1-12")
    year: int = Field(..., ge=2000, le=2098, description="4-digit year")
    mess: str = Field(..., description="Mess ID, e.g. 'kadamba-nonveg'")


class DeleteMonthlyRegInput(AuthInput):
    month: int = Field(..., ge=1, le=12, description="Month 1-12")
    year: int = Field(..., ge=2000, le=2098, description="4-digit year")


class CancellationsInput(AuthInput):
    meal: Meal = Field(..., description="Meal name")
    month: Optional[int] = Field(default=None, ge=1, le=12, description="Month 1-12. Defaults to current.")
    year: Optional[int] = Field(default=None, ge=2000, le=2028, description="Year. Defaults to current.")


class ScansInput(BaseModel):
    model_config = cfg
    meal: Meal = Field(..., description="Meal name")
    mess: str = Field(..., description="Mess ID, e.g. 'yuktahar'")
    date: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")


class ListExtrasInput(BaseModel):
    model_config = cfg
    meal: Meal = Field(..., description="Meal name")
    date: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")
    mess: Optional[str] = Field(default=None, description="Mess ID. If omitted, returns all messes.")


class GetRegisteredExtrasInput(AuthInput):
    meal: Meal = Field(..., description="Meal name")
    date: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")


class CreateExtraRegInput(AuthInput):
    extra: str = Field(..., description="ID of the extra item to register for")
    meal_date: str = Field(..., description="Date YYYY-MM-DD")
    meal_type: Meal = Field(..., description="Meal: breakfast, lunch, snacks, or dinner")
    meal_mess: str = Field(..., description="Mess ID, e.g. 'kadamba-nonveg'")


class DeleteExtraRegInput(AuthInput):
    id: str = Field(..., description="ID of the extra registration to delete")


class ExtrasRangeInput(AuthInput):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", populate_by_name=True)
    from_date: str = Field(..., alias="from", description="Start date YYYY-MM-DD (inclusive)")
    to_date: str = Field(..., alias="to", description="End date YYYY-MM-DD (inclusive, max 2 months)")


class MaxCancellationsInput(AuthInput):
    meal: Meal = Field(..., description="Meal name")


class MealTimingsInput(BaseModel):
    model_config = cfg
    on: Optional[str] = Field(default=None, description="Date YYYY-MM-DD. Defaults to today.")


class UserPreferencesInput(AuthInput):
    notify_not_registered: bool = Field(..., description="Remind before registration deadline")
    notify_malloc_happened: bool = Field(..., description="Email meals if randomly allocated")
    auto_reset_token_daily: bool = Field(..., description="Auto-reset QR at 02:00 daily")
    enable_unregistered: bool = Field(..., description="Allow on-spot availing at unregistered rates")
    nag_for_feedback: bool = Field(..., description="Prompt for feedback after every availed meal")


# ─────────────────────────────────────────────
# AUTHENTICATION TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_cas_login_info",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def mess_cas_login_info() -> str:
    """Get instructions for IIIT student CAS login (browser-only, cannot be called via API/AJAX).

    Returns:
        str: Step-by-step instructions for obtaining a session cookie
    """
    return json.dumps({
        "info": "IIIT CAS login requires a browser redirect — it cannot be called programmatically.",
        "steps": [
            "1. Open https://mess.iiit.ac.in in your browser on VPN and log in via CAS",
            "2. Open DevTools (F12) → Application tab → Cookies → mess.iiit.ac.in",
            "3. Copy the value of the 'session' cookie",
            "4. Pass it as the 'session' parameter in any authenticated tool call"
        ]
    }, indent=2)


@mcp.tool(name="mess_login_msit",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_login_msit(params: MsitLoginInput) -> str:
    """Login as an MSIT student or intern using email + password.

    Args:
        params: user (email address), password

    Returns:
        str: JSON User object. 'session_hint' contains the session cookie value
             to pass as 'session' in subsequent tool calls.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/auth/login/pass",
            json={"user": params.user, "pass": params.password}
        )
        try:
            resp.raise_for_status()
            data = resp.json()
            sc = resp.cookies.get("session")
            if sc:
                data["session_hint"] = {"session": sc, "usage": "Pass as 'session' in other tools"}
            return _out(data)
        except httpx.HTTPStatusError as e:
            try:
                return _out({"http_error": e.response.status_code, "detail": e.response.json()})
            except Exception:
                return _out({"http_error": e.response.status_code, "detail": e.response.text})


@mcp.tool(name="mess_get_me",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_me(params: AuthInput) -> str:
    """Get the currently logged-in user's profile.

    Args:
        params: auth_key or session

    Returns:
        str: JSON User object (id, name, email, roll_number, token, attributes, tags)
    """
    return _out(await _req("GET", "/auth/me", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_auth_keys",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_auth_keys(params: AuthInput) -> str:
    """Get all auth keys for the current user (including expired ones).

    Args:
        params: auth_key or session

    Returns:
        str: JSON array of AuthKey objects (name, user_id, created_at, expires_at)
    """
    return _out(await _req("GET", "/auth/keys", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_create_auth_key",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_create_auth_key(params: CreateAuthKeyInput) -> str:
    """Create a new API auth key. Key names must be unique.

    Args:
        params: auth_key/session, name (unique friendly name), expiry (YYYY-MM-DD)

    Returns:
        str: JSON AuthKey including the key value — save this, it won't be shown again.
             Returns 409 if a key with the same name already exists.
    """
    return _out(await _req(
        "POST", "/auth/keys",
        auth_key=params.auth_key, session=params.session,
        body={"name": params.name, "expiry": params.expiry}
    ))


@mcp.tool(name="mess_get_auth_key_info",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_auth_key_info(params: AuthInput) -> str:
    """Get info about the auth key currently in use (passed in Authorization header).

    Args:
        params: auth_key (the key to inspect)

    Returns:
        str: JSON AuthKey details. Returns 401/403 if the key is expired.
    """
    return _out(await _req("GET", "/auth/keys/info", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_delete_auth_key",
          annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
async def mess_delete_auth_key(params: AuthKeyNameInput) -> str:
    """Delete an auth key by its name (not its value). Identified by name in the URL path.

    Args:
        params: auth_key/session for auth, name = the friendly name of the key to delete

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "DELETE", f"/auth/keys/{params.name}",
        auth_key=params.auth_key, session=params.session
    ))


@mcp.tool(name="mess_reset_qr_token",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_reset_qr_token(params: AuthInput) -> str:
    """Reset the user's QR code token (shown at the mess counter).

    Args:
        params: auth_key or session

    Returns:
        str: JSON { token: string } — new URL-safe base64 token
    """
    return _out(await _req("POST", "/auth/reset-token", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_generate_reset_password_otp",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_generate_reset_password_otp(params: ResetPassInput) -> str:
    """Send a password reset OTP to the given email. Only for MSIT/intern accounts.

    Rate limited to once per minute. Returns 204 even if email is invalid.

    Args:
        params: email address

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req("POST", "/auth/reset-pass", body={"email": params.email}))


@mcp.tool(name="mess_complete_password_reset",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_complete_password_reset(params: ResetPassVerifyInput) -> str:
    """Complete password reset with OTP + new password.

    Args:
        params: email, otp (6-digit string e.g. '123456'), password (new password)

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "POST", "/auth/reset-pass/verify",
        body={"email": params.email, "otp": params.otp, "password": params.password}
    ))


# ─────────────────────────────────────────────
# MESS INFO TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_get_info",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_info(params: AuthInput) -> str:
    """Get info about all messes (name, short_name, color, tags, rating, billing_id). No rates.

    Args:
        params: auth_key or session

    Returns:
        str: JSON array of MessInfo objects
    """
    return _out(await _req("GET", "/mess/info", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_menus",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_menus(params: MessMenuInput) -> str:
    """Get mess menus for a date (all messes returned). No auth required.

    Menu structure per mess: { day_name: { meal: [{ category, name }] } }
    Menus are stored week-wise (Sunday-anchored). effective_from always falls on a Sunday.

    Args:
        params: on (YYYY-MM-DD, optional, defaults to today)

    Returns:
        str: JSON array of { mess, updated_at, effective_from, days }
    """
    return _out(await _req("GET", "/mess/menus", params={"on": params.on}))


@mcp.tool(name="mess_get_rates",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_rates(params: MessMealDateInput) -> str:
    """Get mess rates (in paise) for a meal on a date, grouped by category.

    Categories: registered, unregistered, guest, extra.

    Args:
        params: meal (required), on (YYYY-MM-DD, optional)

    Returns:
        str: JSON { category: [{ mess, day, rate }] } — rate in paise
    """
    return _out(await _req("GET", "/mess/rates", params={"meal": params.meal, "on": params.on}))


@mcp.tool(name="mess_get_capacities",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_capacities(params: MessMealDateInput) -> str:
    """Get mess capacities for a meal on a date, grouped by category.

    Args:
        params: meal (required), on (YYYY-MM-DD, optional)

    Returns:
        str: JSON { category: [{ mess, available, capacity }] }
    """
    return _out(await _req("GET", "/mess/capacities", params={"meal": params.meal, "on": params.on}))


# ─────────────────────────────────────────────
# REGISTRATION TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_get_registrations",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_registrations(params: GetRegistrationsInput) -> str:
    """Get all meal registrations in a date range (max 2 months, both dates inclusive).

    Args:
        params: auth_key/session, from (YYYY-MM-DD), to (YYYY-MM-DD)

    Returns:
        str: JSON array of MealRegistration objects
             (meal_date, meal_type, meal_mess, category, user_id,
              registered_at, cancelled_at, availed_at, availed_price, monthly_reg)
    """
    return _out(await _req(
        "GET", "/registrations",
        auth_key=params.auth_key, session=params.session,
        params={"from": params.from_date, "to": params.to_date}
    ))


@mcp.tool(name="mess_create_registration",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_create_registration(params: CreateRegistrationInput) -> str:
    """Register for a meal, or update an existing registration.

    Fails with 403 (window-closed or capacity-exceeded) if not possible.

    Args:
        params: auth_key/session, meal_date, meal_type, meal_mess, optional guests (int)

    Returns:
        str: JSON MealRegistration on success, or 204 if already registered
    """
    return _out(await _req(
        "POST", "/registrations",
        auth_key=params.auth_key, session=params.session,
        body={
            "meal_date": params.meal_date,
            "meal_type": params.meal_type,
            "meal_mess": params.meal_mess,
            "guests": params.guests,
        }
    ))


@mcp.tool(name="mess_get_registration",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_registration(params: GetOneRegistrationInput) -> str:
    """Get registration(s) for a date. Only returns registered (non-cancelled) meals.

    If meal is omitted, returns { meal_type: MealRegistration } for all meals on that date.
    If date is omitted, defaults to today.

    Args:
        params: auth_key/session, optional meal, optional date (YYYY-MM-DD)

    Returns:
        str: JSON MealRegistration or object keyed by meal name
    """
    return _out(await _req(
        "GET", "/registration",
        auth_key=params.auth_key, session=params.session,
        params={"meal": params.meal.value if params.meal else None, "date": params.date}
    ))


@mcp.tool(name="mess_skip_meal",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_skip_meal(params: SkipMealInput) -> str:
    """Mark a registration as skipped or unskipped.

    Skipping = user likely won't attend but is still charged.
    Use when out of free cancellations.

    Args:
        params: auth_key/session, meal_date, meal_type, meal_mess, skipping (bool)

    Returns:
        str: JSON updated MealRegistration
    """
    return _out(await _req(
        "POST", "/registrations/skipping",
        auth_key=params.auth_key, session=params.session,
        body={
            "meal_date": params.meal_date,
            "meal_type": params.meal_type,
            "meal_mess": params.meal_mess,
            "skipping": params.skipping,
        }
    ))


@mcp.tool(name="mess_cancel_registration",
          annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
async def mess_cancel_registration(params: MealDateTypeInput) -> str:
    """Cancel a meal registration.

    Returns 403 if cancellation window is closed, 424 if no registration exists.

    Args:
        params: auth_key/session, meal_date, meal_type

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "POST", "/registrations/cancel",
        auth_key=params.auth_key, session=params.session,
        body={"meal_date": params.meal_date, "meal_type": params.meal_type}
    ))


@mcp.tool(name="mess_uncancel_registration",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_uncancel_registration(params: MealDateTypeInput) -> str:
    """Restore a previously cancelled meal registration.

    Returns 424 if the registration was not cancelled.

    Args:
        params: auth_key/session, meal_date, meal_type

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "POST", "/registrations/uncancel",
        auth_key=params.auth_key, session=params.session,
        body={"meal_date": params.meal_date, "meal_type": params.meal_type}
    ))


@mcp.tool(name="mess_provide_feedback",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_provide_feedback(params: FeedbackInput) -> str:
    """Submit anonymous feedback for a meal. User must have availed the meal.

    Returns 409 if feedback already submitted, 424 if meal not availed.

    Args:
        params: auth_key/session, meal_date, meal_type, rating (1-5), optional remarks

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "POST", "/registrations/feedback",
        auth_key=params.auth_key, session=params.session,
        body={
            "meal_date": params.meal_date,
            "meal_type": params.meal_type,
            "rating": params.rating,
            "remarks": params.remarks,
        }
    ))


@mcp.tool(name="mess_get_meal_rating",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_meal_rating(params: MealRatingInput) -> str:
    """Get the average rating for a meal at a mess on a date.

    If mess is omitted, returns ratings keyed by mess ID.
    Ratings are only visible after the feedback window closes (403 otherwise).

    Args:
        params: auth_key/session, meal (required), optional mess, optional date

    Returns:
        str: JSON { rating: float, count: int } or { mess_id: { rating, count } }
    """
    return _out(await _req(
        "GET", "/registration/rating",
        auth_key=params.auth_key, session=params.session,
        params={"meal": params.meal, "mess": params.mess, "date": params.date}
    ))


@mcp.tool(name="mess_get_monthly_registration",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_monthly_registration(params: MonthYearInput) -> str:
    """Get the monthly mess registration for the current user.

    Also returns snack availments for the month.

    Args:
        params: auth_key/session, optional month (1-12), optional year

    Returns:
        str: JSON { registration: MonthlyRegistration, snack_availments: [...] }
    """
    return _out(await _req(
        "GET", "/registrations/monthly",
        auth_key=params.auth_key, session=params.session,
        params={"month": params.month, "year": params.year}
    ))


@mcp.tool(name="mess_create_monthly_registration",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_create_monthly_registration(params: CreateMonthlyRegInput) -> str:
    """Register at a mess for an entire month.

    Returns 409 if already registered, 403 if window closed or mess full.

    Args:
        params: auth_key/session, month (1-12), year, mess (mess ID)

    Returns:
        str: JSON MonthlyRegistration object
    """
    return _out(await _req(
        "POST", "/registrations/monthly",
        auth_key=params.auth_key, session=params.session,
        body={"month": params.month, "year": params.year, "mess": params.mess}
    ))


@mcp.tool(name="mess_delete_monthly_registration",
          annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
async def mess_delete_monthly_registration(params: DeleteMonthlyRegInput) -> str:
    """Delete a monthly mess registration (individual meal registrations are kept).

    Returns 403 if window closed.

    Args:
        params: auth_key/session, month (1-12), year

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "DELETE", "/registrations/monthly",
        auth_key=params.auth_key, session=params.session,
        params={"month": params.month, "year": params.year}
    ))


@mcp.tool(name="mess_get_cancellations_count",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_cancellations_count(params: CancellationsInput) -> str:
    """Get count of cancelled registrations for a meal in a month.

    Args:
        params: auth_key/session, meal (required), optional month, optional year

    Returns:
        str: JSON integer count
    """
    return _out(await _req(
        "GET", "/registrations/cancellations",
        auth_key=params.auth_key, session=params.session,
        params={"meal": params.meal, "month": params.month, "year": params.year}
    ))


@mcp.tool(name="mess_get_bill",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_bill(params: MonthYearInput) -> str:
    """Get the mess bill for a month (in paise). May be projected (includes future meals).

    Returns 404 if registrations haven't opened for that month.

    Args:
        params: auth_key/session, optional month, optional year

    Returns:
        str: JSON { non_projected: int, projected: int } — in paise (divide by 100 for rupees)
    """
    return _out(await _req(
        "GET", "/registrations/bill",
        auth_key=params.auth_key, session=params.session,
        params={"month": params.month, "year": params.year}
    ))


@mcp.tool(name="mess_get_scans_count",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_scans_count(params: ScansInput) -> str:
    """Get meal availment (scan) count for a mess on a date. No authentication required.

    Args:
        params: meal (required), mess (required), optional date (YYYY-MM-DD)

    Returns:
        str: JSON { meal, mess, date, total: int, recent: int (last 10 min) }
    """
    return _out(await _req(
        "GET", "/registrations/scans",
        params={"meal": params.meal, "mess": params.mess, "date": params.date}
    ))


@mcp.tool(name="mess_get_registered_extras",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_registered_extras(params: GetRegisteredExtrasInput) -> str:
    """Get extra item registrations for the current user for a meal on a date.

    Args:
        params: auth_key/session, meal (required), optional date (YYYY-MM-DD)

    Returns:
        str: JSON array of ExtraRegistration objects
    """
    return _out(await _req(
        "GET", "/registrations/extras",
        auth_key=params.auth_key, session=params.session,
        params={"meal": params.meal, "date": params.date}
    ))


@mcp.tool(name="mess_create_extra_registration",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def mess_create_extra_registration(params: CreateExtraRegInput) -> str:
    """Register for an extra item on a meal.

    User must have a regular registration at that mess for that meal.
    Cannot be modified — delete and recreate if needed.

    Args:
        params: auth_key/session, extra (item ID), meal_date, meal_type, meal_mess

    Returns:
        str: JSON array of ExtraRegistrationInserted objects
    """
    return _out(await _req(
        "POST", "/registrations/extras",
        auth_key=params.auth_key, session=params.session,
        body={
            "extra": params.extra,
            "meal_date": params.meal_date,
            "meal_type": params.meal_type,
            "meal_mess": params.meal_mess,
        }
    ))


@mcp.tool(name="mess_delete_extra_registration",
          annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True})
async def mess_delete_extra_registration(params: DeleteExtraRegInput) -> str:
    """Delete an extra registration by its ID (passed as query param).

    Args:
        params: auth_key/session, id (extra registration ID)

    Returns:
        str: JSON array of remaining ExtraRegistration objects
    """
    return _out(await _req(
        "DELETE", "/registrations/extras",
        auth_key=params.auth_key, session=params.session,
        params={"id": params.id}
    ))


@mcp.tool(name="mess_get_extras_in_range",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_extras_in_range(params: ExtrasRangeInput) -> str:
    """Get all extra registrations in a date range (max 2 months, both inclusive).

    Args:
        params: auth_key/session, from (YYYY-MM-DD), to (YYYY-MM-DD)

    Returns:
        str: JSON array of ExtraRegistration objects
    """
    return _out(await _req(
        "GET", "/registrations/extras/range",
        auth_key=params.auth_key, session=params.session,
        params={"from": params.from_date, "to": params.to_date}
    ))


# ─────────────────────────────────────────────
# EXTRAS TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_list_extras",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_list_extras(params: ListExtrasInput) -> str:
    """List available extra items for a meal on a date.

    Some extras (same ID) may be available across multiple meals.

    Args:
        params: meal (required), optional date (YYYY-MM-DD), optional mess ID

    Returns:
        str: JSON array of ExtraItem objects (id, name, description, rate in paise, mess, food_tags)
    """
    return _out(await _req(
        "GET", "/extras",
        params={"meal": params.meal, "date": params.date, "mess": params.mess}
    ))


# ─────────────────────────────────────────────
# BILLING TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_get_all_bills",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_all_bills(params: AuthInput) -> str:
    """Get bill breakdown for all months with a non-zero bill.

    Includes food_bill, extras_bill, and infra_bill (all in paise).
    Divide by 100 to get rupees.

    Args:
        params: auth_key or session

    Returns:
        str: JSON array of { month, year, food_bill, extras_bill, infra_bill } — all in paise
    """
    return _out(await _req("GET", "/bills", auth_key=params.auth_key, session=params.session))


# ─────────────────────────────────────────────
# CONFIG TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_get_all_windows",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_all_windows(params: AuthInput) -> str:
    """Get all window times in seconds: cancellation, registration, feedback, extras, skip.

    Args:
        params: auth_key or session

    Returns:
        str: JSON { cancellation_window, registration_window, feedback_window, extras_window, skip_window }
    """
    return _out(await _req("GET", "/config/windows", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_registration_window",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_registration_window(params: AuthInput) -> str:
    """Get the registration window time in seconds.

    Args:
        params: auth_key or session

    Returns:
        str: JSON integer (seconds)
    """
    return _out(await _req("GET", "/config/registration-window", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_cancellation_window",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_cancellation_window(params: AuthInput) -> str:
    """Get the cancellation window time in seconds.

    Args:
        params: auth_key or session

    Returns:
        str: JSON integer (seconds)
    """
    return _out(await _req("GET", "/config/cancellation-window", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_feedback_window",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_feedback_window(params: AuthInput) -> str:
    """Get the feedback window time in seconds (time after a meal to submit feedback).

    Args:
        params: auth_key or session

    Returns:
        str: JSON integer (seconds)
    """
    return _out(await _req("GET", "/config/feedback-window", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_extras_window",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_extras_window(params: AuthInput) -> str:
    """Get the extra registration window time in seconds.

    Args:
        params: auth_key or session

    Returns:
        str: JSON integer (seconds)
    """
    return _out(await _req("GET", "/config/extras-window", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_skip_window",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_skip_window(params: AuthInput) -> str:
    """Get the skip window time in seconds.

    Args:
        params: auth_key or session

    Returns:
        str: JSON integer (seconds)
    """
    return _out(await _req("GET", "/config/skip-window", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_registration_max_date",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_registration_max_date(params: AuthInput) -> str:
    """Get the maximum future date allowed for meal registration.

    Args:
        params: auth_key or session

    Returns:
        str: JSON date string (YYYY-MM-DD)
    """
    return _out(await _req("GET", "/config/registration-max-date", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_get_max_cancellations",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_max_cancellations(params: MaxCancellationsInput) -> str:
    """Get the maximum free cancellations allowed per month for a meal.

    Args:
        params: auth_key/session, meal (required)

    Returns:
        str: JSON integer
    """
    return _out(await _req(
        "GET", "/config/max-cancellations",
        auth_key=params.auth_key, session=params.session,
        params={"meal": params.meal}
    ))


@mcp.tool(name="mess_get_meal_timings",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_meal_timings(params: MealTimingsInput) -> str:
    """Get meal timings (start/end times) for each mess on a date.

    Args:
        params: optional on (YYYY-MM-DD), defaults to today

    Returns:
        str: JSON { mess_id: [{ meal, start_time, end_time }] }
    """
    return _out(await _req("GET", "/config/meal-timings", params={"on": params.on}))


# ─────────────────────────────────────────────
# PREFERENCES TOOLS
# ─────────────────────────────────────────────

@mcp.tool(name="mess_get_preferences",
          annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_get_preferences(params: AuthInput) -> str:
    """Get all user preferences.

    Args:
        params: auth_key or session

    Returns:
        str: JSON UserPreferences:
             notify_not_registered, notify_malloc_happened, auto_reset_token_daily,
             enable_unregistered, nag_for_feedback
    """
    return _out(await _req("GET", "/preferences", auth_key=params.auth_key, session=params.session))


@mcp.tool(name="mess_update_preferences",
          annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def mess_update_preferences(params: UserPreferencesInput) -> str:
    """Update all user preferences (full replacement — all 5 fields required).

    Args:
        params: auth_key/session plus all 5 booleans:
          - notify_not_registered: remind before registration deadline
          - notify_malloc_happened: email on random meal allocation
          - auto_reset_token_daily: reset QR at 02:00 daily
          - enable_unregistered: allow on-spot availing at unregistered rates
          - nag_for_feedback: prompt after every availed meal

    Returns:
        str: JSON status 204 on success
    """
    return _out(await _req(
        "PUT", "/preferences",
        auth_key=params.auth_key, session=params.session,
        body={
            "notify_not_registered": params.notify_not_registered,
            "notify_malloc_happened": params.notify_malloc_happened,
            "auto_reset_token_daily": params.auto_reset_token_daily,
            "enable_unregistered": params.enable_unregistered,
            "nag_for_feedback": params.nag_for_feedback,
        }
    ))


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()