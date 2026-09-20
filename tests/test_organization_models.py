"""Tests for database migrations and models."""
from backend.app.models.models import (
    APIKey,
    Asset,
    Organization,
    RoleEnum,
    SubscriptionTier,
    User,
)


def test_organization_crud():
    """Test organization CRUD operations."""
    org = Organization(
        name="Test Org",
        slug="test-org",
        subscription_tier=SubscriptionTier.free
    )
    assert org.name == "Test Org"
    assert org.slug == "test-org"
    assert org.subscription_tier == SubscriptionTier.free

def test_user_creation():
    """Test user model creation."""
    user = User(
        email="test@example.com",
        hashed_password="hashed",
        full_name="Test User",
        role=RoleEnum.admin
    )
    assert user.email == "test@example.com"
    assert user.role == RoleEnum.admin

def test_api_key_model():
    """Test API key model."""
    key = APIKey(
        name="Test Key",
        key_hash="hashed_key",
        organization_id=1,
        scopes=["read", "write"]
    )
    assert key.name == "Test Key"
    assert key.scopes == ["read", "write"]

def test_asset_belongs_to_org():
    """Test asset has organization relationship."""
    asset = Asset(
        name="Test Asset",
        rpm=1750,
        bearing_type="6205",
        organization_id=1
    )
    assert asset.organization_id == 1