"""Jellyseerr switch platform."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jellyseerr switch based on a config entry."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = integration_data["coordinator"]
    api = integration_data["api"]

    entities = [
        JellyseerrAutoApprovalSwitch(coordinator, api, config_entry),
        JellyseerrHighRatedAutoApprovalSwitch(coordinator, api, config_entry),
        JellyseerrTrustedUserAutoApprovalSwitch(coordinator, api, config_entry),
    ]

    async_add_entities(entities)


class JellyseerrAutoApprovalSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Switch to enable/disable auto-approval monitoring."""

    def __init__(self, coordinator, api, config_entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._api = api
        self._attr_name = "Jellyseerr Auto-Approval"
        self._attr_unique_id = f"{config_entry.entry_id}_auto_approval"
        self._attr_icon = "mdi:robot"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }
        self._is_on = False
        self._unsubscribe = None

    async def async_added_to_hass(self) -> None:
        """Restore state when added to hass."""
        await super().async_added_to_hass()
        
        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            self._is_on = True
            self._start_monitoring()

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        self._start_monitoring()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        self._stop_monitoring()
        self.async_write_ha_state()

    def _start_monitoring(self) -> None:
        """Start monitoring for new requests."""
        @callback
        def _handle_new_requests(event):
            """Handle new request events."""
            if self._is_on:
                self.hass.async_create_task(self._process_new_requests(event.data))
        
        self._unsubscribe = self.hass.bus.async_listen(
            f"{DOMAIN}_new_requests",
            _handle_new_requests
        )

    def _stop_monitoring(self) -> None:
        """Stop monitoring for new requests."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    async def _process_new_requests(self, event_data: dict) -> None:
        """Process new requests based on auto-approval rules."""
        # This is the base switch - it doesn't auto-approve by itself
        # Child switches will override this method
        pass

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is being removed."""
        self._stop_monitoring()


class JellyseerrHighRatedAutoApprovalSwitch(JellyseerrAutoApprovalSwitch):
    """Switch to auto-approve high-rated content."""

    def __init__(self, coordinator, api, config_entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, api, config_entry)
        self._attr_name = "Auto-Approve High Rated (7.5+)"
        self._attr_unique_id = f"{config_entry.entry_id}_auto_approve_high_rated"
        self._attr_icon = "mdi:star-check"
        self._rating_threshold = 7.5

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "rating_threshold": self._rating_threshold,
            "description": f"Automatically approves content rated {self._rating_threshold} or higher",
        }

    async def _process_new_requests(self, event_data: dict) -> None:
        """Auto-approve high-rated new requests."""
        new_requests = event_data.get("requests", [])
        
        for request in new_requests:
            if request.get("rating", 0) >= self._rating_threshold:
                _LOGGER.info(f"Auto-approving high-rated content: {request['title']} (★{request['rating']})")
                result = await self._api.async_approve_request(request["id"])
                if result["success"]:
                    # Fire notification event
                    self.hass.bus.async_fire(
                        f"{DOMAIN}_auto_approved",
                        {
                            "request": request,
                            "reason": f"High rating ({request['rating']})",
                        }
                    )


class JellyseerrTrustedUserAutoApprovalSwitch(JellyseerrAutoApprovalSwitch):
    """Switch to auto-approve requests from trusted users."""

    def __init__(self, coordinator, api, config_entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, api, config_entry)
        self._attr_name = "Auto-Approve Trusted Users"
        self._attr_unique_id = f"{config_entry.entry_id}_auto_approve_trusted"
        self._attr_icon = "mdi:account-check"
        # Get trusted users from config entry options or use default
        self._trusted_users = config_entry.options.get("trusted_users", [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "trusted_users": self._trusted_users,
            "description": "Automatically approves requests from trusted users",
        }

    async def _process_new_requests(self, event_data: dict) -> None:
        """Auto-approve requests from trusted users."""
        new_requests = event_data.get("requests", [])
        
        for request in new_requests:
            if request.get("requested_by") in self._trusted_users:
                _LOGGER.info(f"Auto-approving request from trusted user {request['requested_by']}: {request['title']}")
                result = await self._api.async_approve_request(request["id"])
                if result["success"]:
                    # Fire notification event
                    self.hass.bus.async_fire(
                        f"{DOMAIN}_auto_approved",
                        {
                            "request": request,
                            "reason": f"Trusted user ({request['requested_by']})",
                        }
                    )

    def update_trusted_users(self, users: list[str]) -> None:
        """Update the list of trusted users."""
        self._trusted_users = users
        self.async_write_ha_state()