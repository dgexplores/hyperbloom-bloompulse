"""Tests for authentication and authorization."""
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock, patch

from backend.app.auth import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    verify_api_key,
    RoleEnum,
)
from backend.app.models.models import User, APIKey, Organization, RoleEnum, SubscriptionTier, Asset
from backend.app.database import SessionLocal, init_db


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    init_db()
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def test_jwt_token_creation_and_decoding():
    """Test JWT token creation and decoding."""
    data = {"sub": "user-id-123", "role": "admin"}
    token = create_access_token(data)
    assert isinstance(token, str)
    assert len(token) > 0
    
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-id-123"
    assert payload["role"] == "admin"


def test_jwt_token_expiration():
    """Test JWT token expiration."""
    data = {"sub": "user-id-123"}
    expires_delta = timedelta(minutes=-1)  # Already expired
    token = create_access_token(data, expires_delta=expires_delta)
    
    payload = decode_access_token(token)
    assert payload is None  # Should be None for expired token


def test_jwt_invalid_token():
    """Test decoding invalid token."""
    payload = decode_access_token("invalid.token.string")
    assert payload is None


def test_api_key_generation():
    """Test API key generation."""
    api_key, key_hash = generate_api_key()
    assert api_key.startswith("bp_")
    assert len(api_key) > 32
    assert len(key_hash) == 64  # SHA256 hex digest
    
    # Verify the key matches its hash
    assert verify_api_key(api_key, key_hash)
    assert not verify_api_key("wrong_key", key_hash)


def test_api_key_verification():
    """Test API key verification with wrong key."""
    api_key, key_hash = generate_api_key()
    assert verify_api_key(api_key, key_hash)
    assert not verify_api_key("different_key", key_hash)


def test_role_enum():
    """Test RoleEnum values."""
    assert RoleEnum.admin == "admin"
    assert RoleEnum.engineer == "engineer"
    assert RoleEnum.viewer == "viewer"


def test_subscription_tier_enum():
    """Test SubscriptionTier values."""
    assert SubscriptionTier.free == "free"
    assert SubscriptionTier.pro == "pro"
    assert SubscriptionTier.enterprise == "enterprise"


def test_organization_model(db_session):
    """Test Organization model creation."""
    import uuid
    
    org = Organization(
        name=f"Test Organization {uuid.uuid4().hex[:8]}",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        subscription_tier=SubscriptionTier.pro
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    assert org.name.startswith("Test Organization ")
    assert org.slug.startswith("test-org-")
    assert org.subscription_tier == SubscriptionTier.pro


def test_user_model(db_session):
    """Test User model creation."""
    import uuid
    
    # Create organization first
    org = Organization(name=f"Test Org {uuid.uuid4().hex[:8]}", slug=f"test-org-{uuid.uuid4().hex[:8]}", subscription_tier=SubscriptionTier.free)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        full_name="Test User",
        role=RoleEnum.admin,
        organization_id=org.id
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.email.startswith("test-")
    assert user.role == RoleEnum.admin
    assert user.is_active is True


def test_api_key_model(db_session):
    """Test APIKey model creation."""
    import uuid
    
    # Create organization first
    org = Organization(name=f"Test Org {uuid.uuid4().hex[:8]}", slug=f"test-org-{uuid.uuid4().hex[:8]}", subscription_tier=SubscriptionTier.free)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    
    api_key = APIKey(
        name="Test API Key",
        key_hash="hash123",
        organization_id=org.id,
        scopes=["read", "write"]
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    assert api_key.name == "Test API Key"
    assert api_key.scopes == ["read", "write"]
    assert api_key.is_active is True


def test_asset_model(db_session):
    """Test Asset model with organization."""
    import uuid
    
    # Create organization first
    org = Organization(name=f"Test Org {uuid.uuid4().hex[:8]}", slug=f"test-org-{uuid.uuid4().hex[:8]}", subscription_tier=SubscriptionTier.free)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    
    asset = Asset(
        name="Test Asset",
        rpm=1800,
        bearing_type="6206",
        organization_id=org.id
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    assert asset.name == "Test Asset"
    assert asset.rpm == 1800
    assert asset.organization_id == org.id