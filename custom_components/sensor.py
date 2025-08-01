"""Jellyseerr sensor platform."""
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Status mappings
STATUS_NAMES = {
    1: "Pending",
    2: "Approved", 
    3: "Partially Available",
    4: "Processing",
    5: "Available",
}

STATUS_ICONS = {
    1: "mdi:clock-outline",
    2: "mdi:check-circle",
    3: "mdi:progress-download",
    4: "mdi:cog",
    5: "mdi:download",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyseerr sensor based on a config entry."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = integration_data["coordinator"]

    entities = []
    
    # Add status count sensors
    for status_id, status_name in STATUS_NAMES.items():
        entities.append(
            JellyseerrStatusSensor(
                coordinator, config_entry, status_id, status_name
            )
        )
    
    # Add total requests sensor
    entities.append(JellyseerrTotalSensor(coordinator, config_entry))
    
    # Add recent requests sensor
    entities.append(JellyseerrRecentSensor(coordinator, config_entry))

    async_add_entities(entities)


class JellyseerrStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Jellyseerr status sensor."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        status_id: int,
        status_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._status_id = status_id
        self._status_name = status_name
        self._attr_name = f"Jellyseerr {status_name} Requests"
        self._attr_unique_id = f"{config_entry.entry_id}_{status_name.lower()}_requests"
        self._attr_icon = STATUS_ICONS.get(status_id, "mdi:help-circle")

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return 0
        return self.coordinator.data["status_counts"].get(self._status_id, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        # Get detailed requests for this status
        detailed_requests = self.coordinator.data.get("detailed_requests", {})
        requests = detailed_requests.get(self._status_id, [])
        
        return {
            "requests": requests,
            "status_id": self._status_id,
            "status_name": self._status_name,
        }


class JellyseerrTotalSensor(CoordinatorEntity, SensorEntity):
    """Representation of total Jellyseerr requests sensor."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Jellyseerr Total Requests"
        self._attr_unique_id = f"{config_entry.entry_id}_total_requests"
        self._attr_icon = "mdi:format-list-numbered"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return 0
        return self.coordinator.data["total_requests"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        page_info = self.coordinator.data["page_info"]
        status_counts = self.coordinator.data["status_counts"]
        
        return {
            "pages": page_info.get("pages", 0),
            "page_size": page_info.get("pageSize", 0),
            "current_page": page_info.get("page", 0),
            "status_breakdown": {STATUS_NAMES.get(k, f"Status {k}"): v for k, v in status_counts.items()},
        }


class JellyseerrRecentSensor(CoordinatorEntity, SensorEntity):
    """Representation of recent Jellyseerr requests sensor."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Jellyseerr Recent Requests"
        self._attr_unique_id = f"{config_entry.entry_id}_recent_requests"
        self._attr_icon = "mdi:movie-roll"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return "No requests"
        
        recent = self.coordinator.data["recent_requests"]
        if not recent:
            return "No recent requests"
        
        # Return comma-separated list of titles
        titles = [req["title"] for req in recent]
        return ", ".join(titles)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}
        
        return {
            "recent_requests": self.coordinator.data["recent_requests"],
        }
