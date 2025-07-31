"""Jellyseerr integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "jellyseerr"
PLATFORMS = ["sensor"]

DEFAULT_PORT = 5055
DEFAULT_SSL = False
SCAN_INTERVAL = timedelta(minutes=2)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# Service schemas
SERVICE_APPROVE_REQUEST = "approve_request"
SERVICE_DENY_REQUEST = "deny_request"

APPROVE_REQUEST_SCHEMA = vol.Schema({
    vol.Required("request_id"): cv.positive_int,
})

DENY_REQUEST_SCHEMA = vol.Schema({
    vol.Required("request_id"): cv.positive_int,
    vol.Optional("reason", default="Denied via Home Assistant"): str,
})


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
        
        _LOGGER.debug(f"Jellyseerr API URL: {self._base_url}")

    async def async_get_requests(self, take=50):
        """Get requests from Jellyseerr."""
        url = f"{self._base_url}/request"
        headers = {"X-Api-Key": self._api_key}
        params = {"take": take, "sort": "added"}
        
        _LOGGER.debug(f"Making request to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers, params=params) as response:
                    _LOGGER.debug(f"Response status: {response.status}")
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

    async def async_get_movie_details(self, tmdb_id, media_type="movie"):
        """Get movie/TV details from Jellyseerr's TMDB proxy."""
        try:
            if media_type == "tv":
                url = f"{self._base_url}/tv/{tmdb_id}"
            else:
                url = f"{self._base_url}/movie/{tmdb_id}"
            
            headers = {"X-Api-Key": self._api_key}
            
            _LOGGER.debug(f"Fetching details for {media_type} {tmdb_id}: {url}")
            
            async with async_timeout.timeout(8):
                async with self._session.get(url, headers=headers) as response:
                    if response.status == 200:
                        details = await response.json()
                        _LOGGER.debug(f"Got details for {tmdb_id}: {details.get('title') or details.get('name', 'Unknown')}")
                        return details
                    else:
                        _LOGGER.debug(f"Failed to get details for {tmdb_id}: {response.status}")
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug(f"Error fetching details for {tmdb_id}: {err}")
        return None

    async def async_approve_request(self, request_id: int):
        """Approve a request."""
        url = f"{self._base_url}/request/{request_id}/approve"
        headers = {"X-Api-Key": self._api_key, "Content-Type": "application/json"}
        
        _LOGGER.info(f"Approving request {request_id}")
        
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(url, headers=headers, json={}) as response:
                    if response.status == 200:
                        _LOGGER.info(f"Successfully approved request {request_id}")
                        return True
                    else:
                        _LOGGER.error(f"Failed to approve request {request_id}: {response.status}")
                        return False
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Error approving request {request_id}: {err}")
            return False

    async def async_deny_request(self, request_id: int, reason: str = "Denied via Home Assistant"):
        """Deny a request."""
        url = f"{self._base_url}/request/{request_id}/decline"
        headers = {"X-Api-Key": self._api_key, "Content-Type": "application/json"}
        data = {"reason": reason}
        
        _LOGGER.info(f"Denying request {request_id} with reason: {reason}")
        
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        _LOGGER.info(f"Successfully denied request {request_id}")
                        return True
                    else:
                        _LOGGER.error(f"Failed to deny request {request_id}: {response.status}")
                        return False
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Error denying request {request_id}: {err}")
            return False

    async def async_test_connection(self):
        """Test the connection to Jellyseerr."""
        url = f"{self._base_url}/settings/public"
        headers = {"X-Api-Key": self._api_key}
        
        _LOGGER.debug(f"Testing connection to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers) as response:
                    _LOGGER.debug(f"Test connection status: {response.status}")
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
            
            # Get recent requests with enhanced metadata
            recent_requests = []
            detailed_requests_by_status = {}
            
            # Initialize status dictionaries
            for status in [1, 2, 3, 4, 5]:
                detailed_requests_by_status[status] = []
            
            # Process each request and fetch detailed metadata
            _LOGGER.info(f"Fetching detailed metadata for {len(results)} requests...")
            
            # Batch fetch details for better performance
            detail_tasks = []
            request_mappings = []
            
            for request in results:
                media = request.get("media", {})
                tmdb_id = media.get("tmdbId")
                media_type = request.get("type", "movie")
                
                if tmdb_id:
                    task = self.api.async_get_movie_details(tmdb_id, media_type)
                    detail_tasks.append(task)
                    request_mappings.append((request, tmdb_id, media_type))
                else:
                    # No TMDB ID, use basic info
                    request_mappings.append((request, None, media_type))
                    detail_tasks.append(asyncio.create_task(asyncio.coroutine(lambda: None)()))
            
            # Fetch all details concurrently (with limited concurrency)
            semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
            
            async def fetch_with_semaphore(task):
                async with semaphore:
                    return await task
            
            detail_results = await asyncio.gather(*[fetch_with_semaphore(task) for task in detail_tasks], return_exceptions=True)
            
            # Process results with fetched details
            for i, ((request, tmdb_id, media_type), details) in enumerate(zip(request_mappings, detail_results)):
                media = request.get("media", {})
                status = request.get("status", 0)
                
                # Start with basic info
                title = f"TMDB ID: {tmdb_id}" if tmdb_id else "Unknown"
                overview = ""
                release_date = ""
                rating = 0
                genres = []
                poster_url = None
                runtime = 0
                
                # If we got detailed info, use it
                if details and not isinstance(details, Exception):
                    title = details.get("title") or details.get("name", title)
                    overview = details.get("overview", "")
                    release_date = details.get("release_date") or details.get("first_air_date", "")
                    rating = details.get("vote_average", 0)
                    runtime = details.get("runtime", 0)
                    
                    # Extract genres
                    if details.get("genres"):
                        genres = [genre.get("name", "") for genre in details["genres"]]
                    
                    # Build poster URL
                    poster_path = details.get("poster_path")
                    if poster_path:
                        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                
                request_info = {
                    "id": request.get("id"),
                    "title": title,
                    "status": status,
                    "type": media_type,
                    "created_at": request.get("createdAt"),
                    "requested_by": request.get("requestedBy", {}).get("displayName", "Unknown"),
                    "tmdb_id": tmdb_id,
                    "poster_url": poster_url,
                    "overview": overview,
                    "release_date": release_date,
                    "genres": genres,
                    "rating": rating,
                    "runtime": runtime,
                }
                
                # Add to recent requests (first 5)
                if len(recent_requests) < 5:
                    recent_requests.append(request_info)
                
                # Add to status-specific lists (limit to 10 per status)
                if len(detailed_requests_by_status[status]) < 10:
                    detailed_requests_by_status[status].append(request_info)
            
            _LOGGER.info("Finished fetching detailed metadata")
            
            return {
                "status_counts": status_counts,
                "total_requests": page_info.get("results", 0),
                "recent_requests": recent_requests,
                "detailed_requests": detailed_requests_by_status,
                "page_info": page_info,
                "raw_results": results,
            }
            
        except Exception as err:
            _LOGGER.error(f"Error in _async_update_data: {str(err)}")
            raise UpdateFailed(f"Error communicating with Jellyseerr: {err}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jellyseerr from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    ssl = entry.data.get(CONF_SSL, DEFAULT_SSL)
    api_key = entry.data[CONF_API_KEY]

    _LOGGER.info(f"Setting up Jellyseerr: {host}:{port} SSL:{ssl}")

    session = async_get_clientsession(hass)
    api = JellyseerrAPI(session, host, port, ssl, api_key)

    # Test the connection
    if not await api.async_test_connection():
        raise ConfigEntryNotReady("Unable to connect to Jellyseerr")

    coordinator = JellyseerrDataUpdateCoordinator(hass, api)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def async_approve_request(call: ServiceCall):
        """Handle approve request service call."""
        request_id = call.data["request_id"]
        success = await api.async_approve_request(request_id)
        if success:
            # Trigger coordinator refresh to update status
            await coordinator.async_refresh()
        return success

    async def async_deny_request(call: ServiceCall):
        """Handle deny request service call."""
        request_id = call.data["request_id"]
        reason = call.data.get("reason", "Denied via Home Assistant")
        success = await api.async_deny_request(request_id, reason)
        if success:
            # Trigger coordinator refresh to update status
            await coordinator.async_refresh()
        return success

    # Register the services
    hass.services.async_register(
        DOMAIN, SERVICE_APPROVE_REQUEST, async_approve_request, schema=APPROVE_REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DENY_REQUEST, async_deny_request, schema=DENY_REQUEST_SCHEMA
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove services
        hass.services.async_remove(DOMAIN, SERVICE_APPROVE_REQUEST)
        hass.services.async_remove(DOMAIN, SERVICE_DENY_REQUEST)
        
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
