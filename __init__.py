"""Jellyseerr integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "jellyseerr"
PLATFORMS = ["sensor"]

DEFAULT_PORT = 5055
DEFAULT_SSL = False
SCAN_INTERVAL = timedelta(minutes=2)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


class JellyseerrAPI:
    """Handle Jellyseerr API communication."""

    def __init__(self, session, host, port, ssl, api_key):
        """Initialize the API."""
        self._session = session
        self._host = host
        self._port = port
        self._ssl = ssl
        self._api_key = api_key
        
        # Handle reverse proxy case - if host contains protocol, don't add it
        if host.startswith(('http://', 'https://')):
            self._base_url = f"{host}/api/v1"
        else:
            protocol = "https" if ssl else "http"
            if ssl and port == 443:
                # Standard HTTPS port, don't include port number
                self._base_url = f"{protocol}://{host}/api/v1"
            elif not ssl and port == 80:
                # Standard HTTP port, don't include port number  
                self._base_url = f"{protocol}://{host}/api/v1"
            else:
                # Non-standard port, include it
                self._base_url = f"{protocol}://{host}:{port}/api/v1"
        
        _LOGGER.warning(f"Jellyseerr API URL: {self._base_url}")

    async def async_get_requests(self, take=50):
        """Get requests from Jellyseerr."""
        url = f"{self._base_url}/request"
        headers = {"X-Api-Key": self._api_key}
        params = {"take": take, "sort": "added"}
        
        _LOGGER.warning(f"Making request to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers, params=params) as response:
                    _LOGGER.warning(f"Response status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        _LOGGER.error(f"Jellyseerr API error: {response.status}")
                        return None
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to Jellyseerr")
            return None
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error connecting to Jellyseerr: {err}")
            return None

    async def async_test_connection(self):
        """Test the connection to Jellyseerr."""
        url = f"{self._base_url}/settings/public"
        headers = {"X-Api-Key": self._api_key}
        
        _LOGGER.warning(f"Testing connection to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers) as response:
                    _LOGGER.warning(f"Test connection status: {response.status}")
                    return response.status == 200
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Connection test failed: {err}")
            return False


class JellyseerrDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Jellyseerr data."""

    def __init__(self, hass: HomeAssistant, api: JellyseerrAPI):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self):
        """Fetch data from Jellyseerr."""
        try:
            data = await self.api.async_get_requests()
            if data is None:
                raise UpdateFailed("Error communicating with Jellyseerr API")
            
            # Process the data
            results = data.get("results", [])
            page_info = data.get("pageInfo", {})
            
            # Count requests by status
            status_counts = {}
            for request in results:
                status = request.get("status", 0)
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Get recent requests with titles
            recent_requests = []
            for request in results[:5]:
                media = request.get("media", {})
                title = "Unknown"
                
                # Try to get title from different sources
                if "title" in media:
                    title = media["title"]
                elif "tmdbId" in media:
                    title = f"TMDB ID: {media['tmdbId']}"
                
                recent_requests.append({
                    "id": request.get("id"),
                    "title": title,
                    "status": request.get("status", 0),
                    "type": request.get("type", "unknown"),
                    "created_at": request.get("createdAt"),
                    "requested_by": request.get("requestedBy", {}).get("displayName", "Unknown")
                })
            
            return {
                "status_counts": status_counts,
                "total_requests": page_info.get("results", 0),
                "recent_requests": recent_requests,
                "page_info": page_info,
                "raw_results": results,
            }
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Jellyseerr: {err}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jellyseerr from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    ssl = entry.data.get(CONF_SSL, DEFAULT_SSL)
    api_key = entry.data[CONF_API_KEY]

    _LOGGER.warning(f"Setting up Jellyseerr: {host}:{port} SSL:{ssl}")

    session = async_get_clientsession(hass)
    api = JellyseerrAPI(session, host, port, ssl, api_key)

    # Test the connection
    if not await api.async_test_connection():
        raise ConfigEntryNotReady("Unable to connect to Jellyseerr")

    coordinator = JellyseerrDataUpdateCoordinator(hass, api)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
