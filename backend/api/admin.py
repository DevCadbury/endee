# =============================================================================
# api/admin.py — Company Admin Management Routes
# =============================================================================
# All routes require Admin role (admin or superadmin).
# Provides: staff management, company settings, KB entry CRUD, audit access.
# =============================================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.auth import require_admin, require_roles, get_current_user
from services.mongo import (
    create_user,
    list_users,
    update_user,
    disable_user,
    get_company,
    update_company_settings,
    list_kb_entries,
    update_kb_entry,
    delete_kb_entry,
    get_audit_logs,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


def _require_company(user: dict) -> str:
    """Extract company_id from the user JWT, raising 403 for SuperAdmin."""
    company_id = user.get("company_id", "")
    if not company_id:
        raise HTTPException(
            status_code=403,
            detail="SuperAdmin must use /api/v1/superadmin/* endpoints for cross-company operations",
        )
    return company_id


# =============================================================================
# Request Models
# =============================================================================

class CreateStaffRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "staff"   # staff | admin


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    enabled: Optional[bool] = None


class SettingsRequest(BaseModel):
    auto_resolve_threshold: Optional[float] = None
    clarify_threshold: Optional[float] = None
    auto_resolve_auto_close: Optional[bool] = None


class UpdateKBEntryRequest(BaseModel):
    title: Optional[str] = None
    canonical_answer: Optional[str] = None
    tags: Optional[str] = None
    verified: Optional[bool] = None


# =============================================================================
# Staff Management
# =============================================================================

@router.post("/staff")
async def create_staff(
    request: CreateStaffRequest,
    user: dict = Depends(require_admin),
):
    """Create a new staff or sub-admin user for the company."""
    company_id = _require_company(user)

    from services.mongo import get_user_by_email
    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    allowed_roles = {"staff", "admin"}
    if request.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of {allowed_roles}")

    from api.auth import hash_password
    hashed = hash_password(request.password)

    user_info = await create_user(
        email=request.email,
        hashed_password=hashed,
        company_id=company_id,
        role=request.role,
        name=request.name or request.email.split("@")[0],
        created_by=user.get("user_id", ""),
    )

    logger.info(
        f"Admin {user.get('user_id')} created {request.role} "
        f"{request.email} in company {company_id}"
    )
    return {
        "user_id": user_info["user_id"],
        "email": request.email,
        "role": request.role,
        "company_id": company_id,
    }


@router.get("/staff")
async def get_staff(user: dict = Depends(require_admin)):
    """List all users (staff + admin) for the company."""
    company_id = _require_company(user)
    users = await list_users(company_id)
    return {"staff": users, "total": len(users)}


@router.patch("/staff/{target_user_id}")
async def update_staff(
    target_user_id: str,
    request: UpdateUserRequest,
    user: dict = Depends(require_admin),
):
    """Update name, role, or enabled status of a company user."""
    company_id = _require_company(user)

    # Admin cannot escalate another user to superadmin
    if request.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot assign superadmin role")

    data = {k: v for k, v in request.model_dump().items() if v is not None}
    updated = await update_user(target_user_id, company_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated", "user_id": target_user_id}


@router.delete("/staff/{target_user_id}")
async def delete_staff(
    target_user_id: str,
    user: dict = Depends(require_admin),
):
    """Disable a staff user (soft-delete — does not remove from DB)."""
    company_id = _require_company(user)

    # Prevent admin from disabling themselves
    if target_user_id == user.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot disable your own account")

    disabled = await disable_user(target_user_id, company_id)
    if not disabled:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "disabled", "user_id": target_user_id}


# =============================================================================
# Company Settings
# =============================================================================

@router.get("/settings")
async def get_settings_endpoint(user: dict = Depends(require_admin)):
    """Return the company's current settings."""
    company_id = _require_company(user)
    company = await get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "company_id": company_id,
        "name": company.get("name", ""),
        "slug": company.get("slug", ""),
        "settings": company.get("settings", {}),
    }


@router.patch("/settings")
async def update_settings(
    request: SettingsRequest,
    user: dict = Depends(require_admin),
):
    """Update configurable thresholds and flags for the company."""
    company_id = _require_company(user)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No settings provided")

    # Validate threshold ranges
    for key in ("auto_resolve_threshold", "clarify_threshold"):
        if key in data and not (0.0 <= data[key] <= 1.0):
            raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 1")

    updated = await update_company_settings(company_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"status": "updated", "settings": data}


# =============================================================================
# KB Entry Management
# =============================================================================

@router.get("/kb-entries")
async def list_kb(user: dict = Depends(require_admin)):
    """List all KB entries for the company."""
    company_id = _require_company(user)
    entries = await list_kb_entries(company_id)
    return {"kb_entries": entries, "total": len(entries)}


@router.patch("/kb-entries/{entry_id}")
async def update_kb(
    entry_id: str,
    request: UpdateKBEntryRequest,
    user: dict = Depends(require_admin),
):
    """Edit a KB entry's canonical answer, title, tags, or verification status."""
    company_id = _require_company(user)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    updated = await update_kb_entry(entry_id, company_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="KB entry not found")
    return {"status": "updated", "entry_id": entry_id}


@router.delete("/kb-entries/{entry_id}")
async def delete_kb(
    entry_id: str,
    user: dict = Depends(require_admin),
):
    """Delete a KB entry (removes it from the management layer; Endee vectors remain until re-index)."""
    company_id = _require_company(user)
    deleted = await delete_kb_entry(entry_id, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="KB entry not found")
    return {"status": "deleted", "entry_id": entry_id}


# =============================================================================
# Audit Logs (admin view — same as existing /dashboard/audit)
# =============================================================================

@router.get("/audit")
async def get_admin_audit(
    limit: int = 100,
    user: dict = Depends(require_admin),
):
    """Get audit logs for the company (last N events)."""
    company_id = _require_company(user)
    logs = await get_audit_logs(company_id, limit=limit)
    return {"audit_logs": logs, "total": len(logs)}
