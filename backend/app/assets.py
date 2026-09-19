"""Asset registry with in-memory storage (swappable for Postgres in Phase 4)."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional


@dataclass
class Asset:
    """Asset/machine with persisted baseline for drift detection."""
    id: str
    name: str
    rpm: int = 1750
    bearing_type: str = "6205"
    install_date: Optional[str] = None
    baseline: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class AssetRegistry:
    """In-memory asset registry. Swappable for Postgres in Phase 4."""

    def __init__(self):
        self._assets: dict[str, Asset] = {}

    def create(
        self,
        name: str,
        rpm: int = 1750,
        bearing_type: str = "6205",
        install_date: Optional[str] = None,
    ) -> Asset:
        asset_id = str(uuid.uuid4())[:8]
        asset = Asset(
            id=asset_id,
            name=name,
            rpm=rpm,
            bearing_type=bearing_type,
            install_date=install_date,
        )
        self._assets[asset_id] = asset
        return asset

    def get(self, asset_id: str) -> Optional[Asset]:
        return self._assets.get(asset_id)

    def get_by_name(self, name: str) -> Optional[Asset]:
        for asset in self._assets.values():
            if asset.name == name:
                return asset
        return None

    def list(self) -> list[Asset]:
        return list(self._assets.values())

    def update(self, asset_id: str, data: dict[str, Any]) -> Optional[Asset]:
        asset = self._assets.get(asset_id)
        if not asset:
            return None
        for key, value in data.items():
            if hasattr(asset, key) and key != "id":
                setattr(asset, key, value)
        asset.updated_at = datetime.now(UTC).isoformat()
        return asset

    def delete(self, asset_id: str) -> bool:
        if asset_id in self._assets:
            del self._assets[asset_id]
            return True
        return False

    def update_baseline(self, asset_id: str, baseline_update: dict[str, Any]) -> Optional[Asset]:
        """Merge baseline update with exponential moving average for numeric fields."""
        asset = self._assets.get(asset_id)
        if not asset:
            return None

        # EMA alpha for anomaly_index merging
        alpha = 0.3

        for key, value in baseline_update.items():
            if key == "anomaly_index" and key in asset.baseline:
                # Exponential moving average
                old_val = asset.baseline[key]
                if isinstance(old_val, (int, float)) and isinstance(value, (int, float)):
                    asset.baseline[key] = alpha * value + (1 - alpha) * old_val
                else:
                    asset.baseline[key] = value
            elif key == "trend_points":
                # Handle trend_points: convert scalar to list on first append
                existing = asset.baseline.get(key)
                if existing is None:
                    # First value - start a list
                    asset.baseline[key] = [value] if not isinstance(value, list) else value
                elif isinstance(existing, list):
                    if isinstance(value, list):
                        asset.baseline[key] = (existing + value)[-30:]
                    else:
                        existing.append(value)
                        asset.baseline[key] = existing[-30:]
                else:
                    # Existing is scalar, convert to list
                    asset.baseline[key] = [existing, value] if not isinstance(value, list) else [existing] + value
                    asset.baseline[key] = asset.baseline[key][-30:]
            else:
                asset.baseline[key] = value

        asset.updated_at = datetime.now(UTC).isoformat()
        return asset