"""Authentication and authorization for BloomPulse."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.app.database import get_db_dep
from backend.app.models.models import APIKey, Organization, RoleEnum, User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# API Key settings
API_KEY_PREFIX = "bp_"
API_KEY_LENGTH = 32

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def generate_api_key() -> tuple[str, str]:
    """Generate an API key and its hash.
    
    Returns:
        tuple: (api_key, key_hash)
    """
    random_part = secrets.token_urlsafe(API_KEY_LENGTH)
    api_key = f"{API_KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, key_hash


def verify_api_key(api_key: str, key_hash: str) -> bool:
    """Verify an API key against its hash."""
    return hmac.compare_digest(hashlib.sha256(api_key.encode()).hexdigest(), key_hash)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008 - FastAPI idiom
    db: Session = Depends(get_db_dep)  # noqa: B008 - FastAPI idiom
) -> User:
    """Get the current authenticated user from JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str) or not raw_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = raw_sub
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def get_current_org(
    current_user: User = Depends(get_current_user),  # noqa: B008 - FastAPI idiom
) -> Organization:
    """Get the current user's organization."""
    # The user's organization is loaded via relationship
    return current_user.organization


def verify_api_key_header(
    x_api_key: str | None = Header(None, alias="x-api-key"),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db_dep)  # noqa: B008 - FastAPI idiom
) -> tuple[User, Organization]:
    """Verify API key from header (supports both x-api-key and Authorization: Bearer)."""
    api_key = None
    if x_api_key:
        api_key = x_api_key
    elif authorization and authorization.lower().startswith("bearer "):
        api_key = authorization[7:]
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Look up API key by hash
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    api_key_obj = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True,
    ).first()
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check expiration
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last used
    api_key_obj.last_used_at = datetime.now(UTC)
    
    # Return a user-like object for the API key
    # For API keys, we create a synthetic user based on the key's organization
    user = db.query(User).filter(
        User.organization_id == api_key_obj.organization_id,
        User.role == RoleEnum.admin
    ).first()
    
    if not user:
        # Create a synthetic user for the API key
        user = User(
            id=api_key_obj.id,
            email=f"api-{api_key_obj.id}@bloompulse.local",
            hashed_password="",
            full_name=f"API Key: {api_key_obj.name}",
            role=RoleEnum.engineer,
            is_active=True,
            organization_id=api_key_obj.organization_id,
        )
    
    return user, api_key_obj.organization


def require_role(*allowed_roles: RoleEnum):
    """Dependency that requires specific role(s)."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:  # noqa: B008 - FastAPI idiom
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role.value} not authorized. Required: {[r.value for r in allowed_roles]}"
            )
        return current_user
    return role_checker