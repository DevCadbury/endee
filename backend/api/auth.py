# =============================================================================
# api/auth.py — Authentication, JWT, API Key Management, RBAC
# =============================================================================
# Handles company registration (with slug), user login, API key generation,
# and provides RBAC dependency factories for all other routers.
# =============================================================================

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from jose import jwt, JWTError

from core.config import get_settings
from services.mongo import (
    create_company,
    create_user,
    get_user_by_email,
    get_company_by_slug,
    set_company_owner,
    create_api_key,
    validate_api_key,
    list_api_keys,
    delete_api_key,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# =============================================================================
# Request / Response Models
# =============================================================================

class RegisterRequest(BaseModel):
    company_name: str
    email: str
    password: str
    domain: str = ""
    name: str = ""   # optional display name for the admin user


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    """Extended auth response — includes role, user_id, slug for routing."""
    token: str
    company_id: str
    user_id: str
    email: str
    role: str
    slug: str
    login_url: str


class ApiKeyResponse(BaseModel):
    api_key: str
    company_id: str


class CompanyInfoResponse(BaseModel):
    """Public company info returned for the slug-based login page."""
    company_id: str
    name: str
    slug: str


# =============================================================================
# Password Hashing
# =============================================================================

def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# =============================================================================
# JWT Helpers
# =============================================================================

def create_jwt_token(
    email: str,
    company_id: str,
    user_id: str = "",
    role: str = "admin",
) -> str:
    """Create a JWT token with extended claims."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTP 401 on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        # Back-fill role for tokens minted before RBAC (old admin tokens)
        if "role" not in payload:
            payload["role"] = "admin"
        if "user_id" not in payload:
            payload["user_id"] = ""
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# =============================================================================
# Auth Dependencies
# =============================================================================

async def get_current_user(authorization: str = Header(None)) -> dict:
    """
    FastAPI dependency: validates Bearer JWT and returns the decoded payload.

    Payload keys: sub (email), user_id, company_id, role.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    return decode_jwt_token(token)


async def get_company_from_api_key(x_api_key: str = Header(None)) -> str:
    """
    FastAPI dependency: validates X-API-Key and returns the company_id.
    Used for the legacy widget chat endpoint.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header missing")
    company_id = await validate_api_key(x_api_key)
    if not company_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return company_id


def require_roles(*roles: str):
    """
    RBAC dependency factory.

    Usage:
        @router.delete("/kb-entries/{id}")
        async def delete_entry(user=Depends(require_roles("admin", "superadmin"))):
            ...
    """
    async def _check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.get('role')}' is not authorised for this action.",
            )
        return user
    return _check


# Convenience aliases — import these in other routers
require_admin = require_roles("admin", "superadmin")
require_staff = require_roles("staff", "admin", "superadmin")
require_superadmin = require_roles("superadmin")


# =============================================================================
# Routes
# =============================================================================

@router.post("/register")
async def register(request: RegisterRequest):
    """
    Register a new company + admin user.

    Returns a full AuthResponse including company slug and unique login URL.
    """
    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create company (auto-generates unique slug)
    company_info = await create_company(
        name=request.company_name,
        domain=request.domain,
    )
    company_id = company_info["company_id"]
    slug = company_info["slug"]

    # Create admin user
    hashed_pw = hash_password(request.password)
    user_info = await create_user(
        email=request.email,
        hashed_password=hashed_pw,
        company_id=company_id,
        role="admin",
        name=request.name or request.email.split("@")[0],
    )
    user_id = user_info["user_id"]

    # Backfill owner on company
    await set_company_owner(company_id, user_id)

    token = create_jwt_token(request.email, company_id, user_id, "admin")

    logger.info(
        f"Registered company '{request.company_name}' "
        f"(id={company_id}, slug={slug})"
    )

    return {
        "token": token,
        "company_id": company_id,
        "user_id": user_id,
        "email": request.email,
        "role": "admin",
        "slug": slug,
        "login_url": f"/login/{slug}",
    }


@router.post("/login")
async def login(request: LoginRequest):
    """
    Authenticate a user and return a JWT token.

    Works for admin, staff, and superadmin roles.
    """
    user = await get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("enabled", True):
        raise HTTPException(status_code=403, detail="Account disabled")

    role = user.get("role", "admin")
    user_id = user.get("user_id", "")
    company_id = user.get("company_id", "")

    # Resolve company slug for the response
    slug = ""
    if company_id:
        try:
            from bson import ObjectId
            from services.mongo import get_db
            db = get_db()
            company_doc = await db.companies.find_one({"_id": ObjectId(company_id)})
            if company_doc:
                slug = company_doc.get("slug", "")
        except Exception:
            pass

    token = create_jwt_token(user["email"], company_id, user_id, role)

    return {
        "token": token,
        "company_id": company_id,
        "user_id": user_id,
        "email": user["email"],
        "role": role,
        "slug": slug,
        "login_url": f"/login/{slug}" if slug else "/login",
    }


@router.get("/company/{slug}", response_model=CompanyInfoResponse)
async def get_company_info(slug: str):
    """
    Public endpoint — returns company name and ID for the slug-based login page.
    No authentication required.
    """
    company = await get_company_by_slug(slug)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyInfoResponse(
        company_id=company.get("company_id") or company["_id"],
        name=company["name"],
        slug=company["slug"],
    )


@router.post("/api-key", response_model=ApiKeyResponse)
async def generate_api_key(user: dict = Depends(require_admin)):
    """
    Generate a new API key for widget integration.
    Admin and SuperAdmin only.
    """
    company_id = user["company_id"]
    key = f"pk_live_{secrets.token_urlsafe(32)}"
    result = await create_api_key(company_id, key)
    logger.info(f"Generated API key for company {company_id}")
    return ApiKeyResponse(api_key=key, company_id=company_id)


@router.get("/api-keys")
async def get_api_keys(user: dict = Depends(require_admin)):
    """List all API keys for this company (masked). Admin only."""
    company_id = user["company_id"]
    keys = await list_api_keys(company_id)
    return {"api_keys": keys}


@router.delete("/api-key/{key_id}")
async def revoke_api_key(key_id: str, user: dict = Depends(require_admin)):
    """Delete (revoke) an API key. Admin only."""
    company_id = user["company_id"]
    deleted = await delete_api_key(key_id, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")
    logger.info(f"Revoked API key {key_id} for company {company_id}")
    return {"status": "deleted", "key_id": key_id}


@router.post("/superadmin-init")
async def init_superadmin(request: RegisterRequest):
    """
    One-time bootstrap endpoint to create the SuperAdmin account.
    Only works if no superadmin exists yet and the SUPERADMIN_INIT_TOKEN
    environment variable is set.
    """
    import os
    init_token = os.getenv("SUPERADMIN_INIT_TOKEN", "")
    if not init_token:
        raise HTTPException(status_code=403, detail="SuperAdmin init not enabled")
    if request.domain != init_token:
        raise HTTPException(status_code=403, detail="Invalid init token")

    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    from services.mongo import get_db
    db = get_db()
    existing_sa = await db.users.find_one({"role": "superadmin"})
    if existing_sa:
        raise HTTPException(status_code=400, detail="SuperAdmin already exists")

    hashed_pw = hash_password(request.password)
    user_info = await create_user(
        email=request.email,
        hashed_password=hashed_pw,
        company_id="",   # SuperAdmin has no company
        role="superadmin",
        name=request.name or "SuperAdmin",
    )

    token = create_jwt_token(request.email, "", user_info["user_id"], "superadmin")
    logger.info(f"SuperAdmin account created: {request.email}")
    return {"token": token, "user_id": user_info["user_id"], "role": "superadmin"}
