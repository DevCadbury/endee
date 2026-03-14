# =============================================================================
# tests/test_auth_rbac.py — Authentication & RBAC Tests
# =============================================================================
# Covers:
#   - Company registration (slug generation, login_url, duplicate guard)
#   - Login (credentials, disabled accounts, role + slug in response)
#   - Public company-info endpoint
#   - JWT encode/decode
#   - RBAC dependency enforcement (require_staff, require_admin, require_superadmin)
#   - SuperAdmin guard (_require_company) on admin-scoped endpoints
# =============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from api.auth import (
    create_jwt_token,
    decode_jwt_token,
    hash_password,
    verify_password,
    require_roles,
    require_staff,
    require_admin,
    require_superadmin,
    register,
    login,
    get_company_info,
    RegisterRequest,
    LoginRequest,
)
from api.admin import _require_company


# =============================================================================
# Password Hashing
# =============================================================================

class TestPasswordHashing:

    def test_hash_and_verify(self):
        """Hashed password should verify correctly."""
        pw = "super-secret-123"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        """Wrong password should not verify."""
        hashed = hash_password("correct-horse")
        assert not verify_password("wrong-horse", hashed)

    def test_unique_hashes(self):
        """Each hash call should produce a unique salt."""
        h1 = hash_password("same-pw")
        h2 = hash_password("same-pw")
        assert h1 != h2  # bcrypt includes random salt


# =============================================================================
# JWT Helpers
# =============================================================================

class TestJWT:

    def test_encode_decode_roundtrip(self):
        """Encoded JWT should decode back to the same payload."""
        token = create_jwt_token("admin@co.com", "co_123", "u_1", "admin")
        payload = decode_jwt_token(token)
        assert payload["sub"] == "admin@co.com"
        assert payload["company_id"] == "co_123"
        assert payload["user_id"] == "u_1"
        assert payload["role"] == "admin"

    def test_invalid_token_raises_401(self):
        """Garbage token should raise HTTP 401."""
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt_token("not.a.token")
        assert exc_info.value.status_code == 401

    def test_old_token_backfills_role(self):
        """Token without 'role' key should default to 'admin'."""
        from core.config import get_settings
        from jose import jwt as jose_jwt
        from datetime import datetime, timezone, timedelta
        settings = get_settings()
        payload = {
            "sub": "legacy@co.com",
            "company_id": "co_old",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        token = jose_jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        decoded = decode_jwt_token(token)
        assert decoded["role"] == "admin"
        assert decoded["user_id"] == ""


# =============================================================================
# RBAC Dependencies
# =============================================================================

class TestRBACDependencies:
    """Test the require_roles() factory and its convenience aliases."""

    @pytest.mark.asyncio
    async def test_staff_passes_require_staff(self):
        """Staff role should pass require_staff."""
        user = {"role": "staff", "user_id": "u1", "company_id": "co1"}
        result = await require_staff(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_admin_passes_require_staff(self):
        """Admin role should also pass require_staff (staff ∪ admin ∪ superadmin)."""
        user = {"role": "admin", "user_id": "u2", "company_id": "co1"}
        result = await require_staff(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_staff_fails_require_admin(self):
        """Staff role must be rejected by require_admin."""
        user = {"role": "staff", "user_id": "u1", "company_id": "co1"}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_passes_require_admin(self):
        """Admin role should pass require_admin."""
        user = {"role": "admin", "user_id": "u2", "company_id": "co1"}
        result = await require_admin(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_superadmin_passes_require_admin(self):
        """SuperAdmin role should also pass require_admin."""
        user = {"role": "superadmin", "user_id": "u3", "company_id": ""}
        result = await require_admin(user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_admin_fails_require_superadmin(self):
        """Admin role must be rejected by require_superadmin."""
        user = {"role": "admin", "user_id": "u2", "company_id": "co1"}
        with pytest.raises(HTTPException) as exc_info:
            await require_superadmin(user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_superadmin_passes_require_superadmin(self):
        """SuperAdmin role should pass require_superadmin."""
        user = {"role": "superadmin", "user_id": "u3", "company_id": ""}
        result = await require_superadmin(user=user)
        assert result == user

    def test_superadmin_blocked_from_admin_endpoints(self):
        """
        _require_company() must raise 403 if company_id is empty.
        SuperAdmin has no company_id and must use /superadmin/* instead.
        """
        superadmin_user = {"role": "superadmin", "user_id": "u3", "company_id": ""}
        with pytest.raises(HTTPException) as exc_info:
            _require_company(superadmin_user)
        assert exc_info.value.status_code == 403
        assert "superadmin" in exc_info.value.detail.lower()

    def test_admin_allowed_by_require_company(self):
        """Normal admin with a company_id should pass _require_company."""
        admin_user = {"role": "admin", "user_id": "u2", "company_id": "co_123"}
        company_id = _require_company(admin_user)
        assert company_id == "co_123"


# =============================================================================
# Registration Endpoint
# =============================================================================

class TestRegistration:

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock, return_value=None)
    @patch("api.auth.create_company", new_callable=AsyncMock)
    @patch("api.auth.create_user", new_callable=AsyncMock)
    @patch("api.auth.set_company_owner", new_callable=AsyncMock)
    async def test_successful_registration(
        self, mock_owner, mock_create_user, mock_create_company, mock_get_user
    ):
        """Successful registration returns slug, login_url, role, and token."""
        mock_create_company.return_value = {"company_id": "co_abc", "slug": "acme-corp"}
        mock_create_user.return_value = {"user_id": "user_xyz"}

        result = await register(RegisterRequest(
            company_name="Acme Corp",
            email="admin@acme.com",
            password="strong-pass-1",
        ))

        assert result["slug"] == "acme-corp"
        assert result["login_url"] == "/login/acme-corp"
        assert result["role"] == "admin"
        assert result["company_id"] == "co_abc"
        assert result["user_id"] == "user_xyz"
        assert "token" in result

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock)
    async def test_duplicate_email_raises_400(self, mock_get_user):
        """Registering with an already-used email must return 400."""
        mock_get_user.return_value = {"email": "existing@co.com"}

        with pytest.raises(HTTPException) as exc_info:
            await register(RegisterRequest(
                company_name="Dupe Corp",
                email="existing@co.com",
                password="pass",
            ))
        assert exc_info.value.status_code == 400
        assert "already registered" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock, return_value=None)
    @patch("api.auth.create_company", new_callable=AsyncMock)
    @patch("api.auth.create_user", new_callable=AsyncMock)
    @patch("api.auth.set_company_owner", new_callable=AsyncMock)
    async def test_slug_is_url_safe(
        self, mock_owner, mock_create_user, mock_create_company, mock_get_user
    ):
        """Slug should only contain lowercase letters, digits, hyphens."""
        import re
        mock_create_company.return_value = {
            "company_id": "co_1",
            "slug": "my-company-ltd",
        }
        mock_create_user.return_value = {"user_id": "u1"}

        result = await register(RegisterRequest(
            company_name="My Company Ltd.",
            email="a@b.com",
            password="x",
        ))

        assert re.match(r"^[a-z0-9-]+$", result["slug"]), (
            f"Slug '{result['slug']}' is not URL-safe"
        )


# =============================================================================
# Login Endpoint
# =============================================================================

class TestLogin:

    def _make_db_user(self, role="admin", enabled=True):
        return {
            "email": "test@co.com",
            "hashed_password": hash_password("correct-password"),
            "role": role,
            "user_id": "user_001",
            "company_id": "co_001",
            "enabled": enabled,
        }

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock)
    async def test_successful_login(self, mock_get_user):
        """Successful login returns token, role, and user_id."""
        mock_get_user.return_value = self._make_db_user()

        # login() imports get_db lazily inside the function body
        with patch("services.mongo.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.companies.find_one = AsyncMock(return_value={"slug": "acme-corp"})
            mock_get_db.return_value = mock_db

            result = await login(LoginRequest(
                email="test@co.com",
                password="correct-password",
            ))

        assert "token" in result
        assert result["role"] == "admin"
        assert result["user_id"] == "user_001"

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock)
    async def test_wrong_password_raises_401(self, mock_get_user):
        """Wrong password must return 401."""
        mock_get_user.return_value = self._make_db_user()

        with pytest.raises(HTTPException) as exc_info:
            await login(LoginRequest(email="test@co.com", password="wrong-password"))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock, return_value=None)
    async def test_unknown_email_raises_401(self, mock_get_user):
        """Unknown email must return 401 (no user found)."""
        with pytest.raises(HTTPException) as exc_info:
            await login(LoginRequest(email="ghost@nowhere.com", password="pass"))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock)
    async def test_disabled_account_raises_403(self, mock_get_user):
        """Disabled accounts must be rejected with 403."""
        mock_get_user.return_value = self._make_db_user(enabled=False)

        with pytest.raises(HTTPException) as exc_info:
            await login(LoginRequest(email="test@co.com", password="correct-password"))
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("api.auth.get_user_by_email", new_callable=AsyncMock)
    async def test_staff_login_returns_staff_role(self, mock_get_user):
        """Staff user login must return role='staff' in the response."""
        mock_get_user.return_value = self._make_db_user(role="staff")

        with patch("services.mongo.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.companies.find_one = AsyncMock(return_value={"slug": "acme-corp"})
            mock_get_db.return_value = mock_db

            result = await login(LoginRequest(email="test@co.com", password="correct-password"))

        assert result["role"] == "staff"


# =============================================================================
# Public company-info Endpoint
# =============================================================================

class TestCompanyInfo:

    @pytest.mark.asyncio
    @patch("api.auth.get_company_by_slug", new_callable=AsyncMock)
    async def test_known_slug_returns_company_name(self, mock_get):
        """GET /auth/company/{slug} should return the company name."""
        mock_get.return_value = {
            "_id": "co_123",
            "company_id": "co_123",
            "name": "Acme Corp",
            "slug": "acme-corp",
        }
        result = await get_company_info("acme-corp")
        assert result.name == "Acme Corp"
        assert result.slug == "acme-corp"

    @pytest.mark.asyncio
    @patch("api.auth.get_company_by_slug", new_callable=AsyncMock, return_value=None)
    async def test_unknown_slug_raises_404(self, mock_get):
        """Unknown slug must return 404."""
        with pytest.raises(HTTPException) as exc_info:
            await get_company_info("does-not-exist")
        assert exc_info.value.status_code == 404
