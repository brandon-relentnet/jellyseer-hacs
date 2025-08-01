"""Jellyseerr button platform."""
import asyncio
import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyseerr button based on a config entry."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = integration_data["coordinator"]
    api = integration_data["api"]

    entities = [
        JellyseerrRefreshButton(coordinator, config_entry),
        JellyseerrApproveAllButton(coordinator, api, config_entry),
        JellyseerrAutoApproveHighRatedButton(coordinator, api, config_entry),
    ]

    async_add_entities(entities)


class JellyseerrRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to refresh Jellyseerr data."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_name = "Jellyseerr Refresh"
        self._attr_unique_id = f"{config_entry.entry_id}_refresh"
        self._attr_icon = "mdi:refresh"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"Jellyseerr",
            "manufacturer": "Jellyseerr",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()


class JellyseerrApproveAllButton(CoordinatorEntity, ButtonEntity):
    """Button to approve all pending requests."""

    def __init__(self, coordinator, api, config_entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._api = api
        self._attr_name = "Approve All Pending"
        self._attr_unique_id = f"{config_entry.entry_id}_approve_all"
        self._attr_icon = "mdi:check-all"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("status_counts", {}).get(1, 0) > 0

    async def async_press(self) -> None:
        """Handle the button press."""
        if not self.coordinator.data:
            return
        
        detailed_requests = self.coordinator.data.get("detailed_requests", {})
        pending_requests = detailed_requests.get(1, [])
        
        approved_count = 0
        failed_count = 0
        
        for request in pending_requests:
            result = await self._api.async_approve_request(request["id"])
            if result["success"]:
                approved_count += 1
            else:
                failed_count += 1
            # Small delay between requests
            await asyncio.sleep(0.5)
        
        _LOGGER.info(f"Batch approval complete: {approved_count} approved, {failed_count} failed")
        
        # Refresh data
        await self.coordinator.async_request_refresh()


class JellyseerrAutoApproveHighRatedButton(CoordinatorEntity, ButtonEntity):
    """Button to auto-approve high-rated content."""

    def __init__(self, coordinator, api, config_entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._api = api
        self._attr_name = "Auto-Approve High Rated"
        self._attr_unique_id = f"{config_entry.entry_id}_auto_approve_high"
        self._attr_icon = "mdi:star-check"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.data:
            return False
        
        # Check if there are any high-rated pending requests
        detailed_requests = self.coordinator.data.get("detailed_requests", {})
        pending_requests = detailed_requests.get(1, [])
        return any(req.get("rating", 0) >= 7.5 for req in pending_requests)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        
        detailed_requests = self.coordinator.data.get("detailed_requests", {})
        pending_requests = detailed_requests.get(1, [])
        high_rated = [req for req in pending_requests if req.get("rating", 0) >= 7.5]
        
        return {
            "high_rated_count": len(high_rated),
            "high_rated_titles": [req["title"] for req in high_rated],
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        if not self.coordinator.data:
            return
        
        detailed_requests = self.coordinator.data.get("detailed_requests", {})
        pending_requests = detailed_requests.get(1, [])
        high_rated = [req for req in pending_requests if req.get("rating", 0) >= 7.5]
        
        approved_count = 0
        
        for request in high_rated:
            result = await self._api.async_approve_request(request["id"])
            if result["success"]:
                approved_count += 1
                _LOGGER.info(f"Auto-approved high-rated: {request['title']} (★{request['rating']})")
            await asyncio.sleep(0.5)
        
        _LOGGER.info(f"Auto-approved {approved_count} high-rated requests")
        
        # Refresh data
        await self.coordinator.async_request_refresh()