"""Jellyseerr integration for Home Assistant."""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo

_LOGGER = logging.getLogger(__name__)

DOMAIN = "jellyseerr"
PLATFORMS = ["sensor", "button", "switch"]

DEFAULT_PORT = 5055
DEFAULT_SSL = False
SCAN_INTERVAL = timedelta(minutes=2)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

# Service schemas
SERVICE_APPROVE_REQUEST = "approve_request"
SERVICE_DENY_REQUEST = "deny_request"
SERVICE_BATCH_APPROVE = "batch_approve"
SERVICE_BATCH_DENY = "batch_deny"

APPROVE_REQUEST_SCHEMA = vol.Schema({
    vol.Required("request_id"): cv.positive_int,
})

DENY_REQUEST_SCHEMA = vol.Schema({
    vol.Required("request_id"): cv.positive_int,
    vol.Optional("reason", default="Denied via Home Assistant"): cv.string,
})

BATCH_APPROVE_SCHEMA = vol.Schema({
    vol.Required("request_ids"): vol.All(cv.ensure_list, [cv.positive_int]),
})

BATCH_DENY_SCHEMA = vol.Schema({
    vol.Required("request_ids"): vol.All(cv.ensure_list, [cv.positive_int]),
    vol.Optional("reason", default="Denied via Home Assistant"): cv.string,
})

# Custom exceptions
class JellyseerrError(HomeAssistantError):
    """Base error for Jellyseerr integration."""

class JellyseerrConnectionError(JellyseerrError):
    """Error connecting to Jellyseerr."""

class JellyseerrAuthenticationError(JellyseerrError):
    """Error authenticating with Jellyseerr."""


class JellyseerrAPI:
    """Handle Jellyseerr API communication."""

    def __init__(self, session, host, port, ssl, api_key):
        """Initialize the API."""
        self._session = session
        self._host = host
        self._port = port
        self._ssl = ssl
        self._api_key = api_key
        self._server_info = None
        
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

    async def async_get_requests(self, take=50, status=None):
        """Get requests from Jellyseerr with optional status filter."""
        url = f"{self._base_url}/request"
        headers = {"X-Api-Key": self._api_key}
        params = {"take": take, "sort": "added"}
        
        if status is not None:
            params["status"] = status
        
        _LOGGER.debug(f"Making request to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers, params=params) as response:
                    _LOGGER.debug(f"Response status: {response.status}")
                    if response.status == 401:
                        raise JellyseerrAuthenticationError("Invalid API key")
                    elif response.status == 200:
                        data = await response.json()
                        _LOGGER.debug(f"Got {len(data.get('results', []))} requests")
                        return data
                    else:
                        error_text = await response.text()
                        _LOGGER.error(f"Jellyseerr API error: {response.status} - {error_text}")
                        raise JellyseerrError(f"API returned {response.status}")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to Jellyseerr")
            raise JellyseerrConnectionError("Connection timeout")
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error connecting to Jellyseerr: {err}")
            raise JellyseerrConnectionError(str(err))

    async def async_get_media_details(self, request):
        """Get enhanced media details including poster from request data."""
        media = request.get("media", {})
        media_type = request.get("type", "movie")
        
        tmdb_id = media.get("tmdbId")
        if tmdb_id:
            try:
                # Use the new API endpoint
                url = f"https://requests.olvyx.com/api/v1/{media_type}/{tmdb_id}"
                _LOGGER.debug(f"Fetching details from new endpoint: {url}")
                
                async with async_timeout.timeout(8):
                    async with self._session.get(url) as response:
                        if response.status == 200:
                            details = await response.json()
                            _LOGGER.debug(f"Got details for {tmdb_id}: {details.get('title') or details.get('name', 'Unknown')}")
                            
                            # Extract the necessary data from the new JSON response
                            poster_url = f"https://image.tmdb.org/t/p/w500{details['posterPath']}" if details.get("posterPath") else None
                            backdrop_url = f"https://image.tmdb.org/t/p/original{details['backdropPath']}" if details.get("backdropPath") else None
                            
                            return {
                                "poster_url": poster_url,
                                "backdrop_url": backdrop_url,
                                "tmdb_id": tmdb_id,
                                "imdb_id": details.get("imdbId"),
                                "title": details.get("title") or details.get("name"),
                                "overview": details.get("overview"),
                                "release_date": details.get("releaseDate") or details.get("firstAirDate"),
                                "genres": [g.get("name", "") for g in details.get("genres", [])],
                                "rating": details.get("voteAverage", 0),
                                "runtime": details.get("runtime", 0),
                            }
            except Exception as e:
                _LOGGER.error(f"Error fetching details from new API for TMDB ID {tmdb_id}: {e}")

        # Fallback if the new API call fails or tmdb_id is not present
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
                        
                        # Use the correct key, checking for both camelCase and snake_case
                        poster_path = details.get("poster_path") or details.get("posterPath")
                        
                        if poster_path:
                            _LOGGER.debug(f"Found poster path: {poster_path}")
                        else:
                            _LOGGER.warning(f"No poster path found for {tmdb_id}")
                        return details
                    else:
                        _LOGGER.debug(f"Failed to get details for {tmdb_id}: {response.status}")
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug(f"Error fetching details for {tmdb_id}: {err}")
        return None

    async def async_approve_request(self, request_id: int) -> Dict[str, Any]:
        """Approve a request."""
        url = f"{self._base_url}/request/{request_id}/approve"
        headers = {"X-Api-Key": self._api_key, "Content-Type": "application/json"}
        
        _LOGGER.info(f"Approving request {request_id}")
        
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(url, headers=headers, json={}) as response:
                    response_data = await response.json()
                    if response.status == 200:
                        _LOGGER.info(f"Successfully approved request {request_id}")
                        return {"success": True, "data": response_data}
                    else:
                        _LOGGER.error(f"Failed to approve request {request_id}: {response.status}")
                        return {"success": False, "error": response_data.get("message", "Unknown error")}
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Error approving request {request_id}: {err}")
            return {"success": False, "error": str(err)}

    async def async_deny_request(self, request_id: int, reason: str = "Denied via Home Assistant") -> Dict[str, Any]:
        """Deny a request."""
        url = f"{self._base_url}/request/{request_id}/decline"
        headers = {"X-Api-Key": self._api_key, "Content-Type": "application/json"}
        data = {"reason": reason}
        
        _LOGGER.info(f"Denying request {request_id} with reason: {reason}")
        
        try:
            async with async_timeout.timeout(10):
                async with self._session.post(url, headers=headers, json=data) as response:
                    response_data = await response.json()
                    if response.status == 200:
                        _LOGGER.info(f"Successfully denied request {request_id}")
                        return {"success": True, "data": response_data}
                    else:
                        _LOGGER.error(f"Failed to deny request {request_id}: {response.status}")
                        return {"success": False, "error": response_data.get("message", "Unknown error")}
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Error denying request {request_id}: {err}")
            return {"success": False, "error": str(err)}

    async def async_test_connection(self) -> bool:
        """Test the connection to Jellyseerr."""
        url = f"{self._base_url}/settings/public"
        headers = {"X-Api-Key": self._api_key}
        
        _LOGGER.debug(f"Testing connection to: {url}")

        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url, headers=headers) as response:
                    _LOGGER.debug(f"Test connection status: {response.status}")
                    if response.status == 200:
                        self._server_info = await response.json()
                        return True
                    elif response.status == 401:
                        raise JellyseerrAuthenticationError("Invalid API key")
                    return False
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error(f"Connection test failed: {err}")
            raise JellyseerrConnectionError(str(err))

    async def async_get_server_info(self) -> Optional[Dict[str, Any]]:
        """Get server information."""
        if self._server_info is None:
            await self.async_test_connection()
        return self._server_info


class JellyseerrDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Jellyseerr data."""

    def __init__(self, hass: HomeAssistant, api: JellyseerrAPI, entry: ConfigEntry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.entry = entry
        self._last_pending_count = 0

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
            
            # Process each request
            _LOGGER.info(f"Processing {len(results)} requests...")
            
            for request in results:
                media = request.get("media", {})
                status = request.get("status", 0)
                media_type = request.get("type", "movie")
                
                # Initialize with basic info
                title = "Unknown"
                overview = ""
                release_date = ""
                rating = 0
                genres = []
                poster_url = None
                backdrop_url = None
                runtime = 0
                tmdb_id = media.get("tmdbId")
                
                # Use existing media info if available
                if media:
                    title = media.get("title") or media.get("name", title)
                    overview = media.get("overview", "")
                    release_date = media.get("releaseDate") or media.get("firstAirDate", "")
                    rating = media.get("voteAverage", 0)
                    runtime = media.get("runtime", 0)
                    
                    # Extract genres if present
                    if media.get("genres"):
                        genres = [genre.get("name", "") for genre in media["genres"]]

                    # Check for both posterPath (camelCase) and poster_path (snake_case)
                    poster_path = media.get("posterPath") or media.get("poster_path")
                    if poster_path:
                        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                        _LOGGER.debug(f"Using poster from media object for {title}")
                    
                    # Check for both backdropPath (camelCase) and backdrop_path (snake_case)
                    backdrop_path = media.get("backdropPath") or media.get("backdrop_path")
                    if backdrop_path:
                        backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}"
                    
                
                # If we still don't have a poster and have TMDB ID, fetch details
                if not poster_url and tmdb_id:
                    _LOGGER.debug(f"Fetching additional details for {title} (TMDB: {tmdb_id})")
                    details = await self.api.async_get_movie_details(tmdb_id, media_type)
                    
                    if details:
                        # Update with fetched details
                        title = details.get("title") or details.get("name", title)
                        overview = details.get("overview", overview)
                        release_date = details.get("release_date") or details.get("first_air_date", release_date)
                        rating = details.get("vote_average", rating)
                        runtime = details.get("runtime", runtime)
                        
                        # Get poster from fetched details
                        poster_path = details.get("poster_path") or details.get("posterPath")
                        if poster_path:
                            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                            _LOGGER.debug(f"Got poster from API for {title}: {poster_url}")
                        
                        backdrop_path = details.get("backdrop_path") or details.get("backdropPath")
                        if backdrop_path:
                            backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}"
                        
                        # Update genres
                        if details.get("genres"):
                            genres = [genre.get("name", "") for genre in details["genres"]]
                
                # Log if we still don't have a poster
                if not poster_url:
                    _LOGGER.warning(f"No poster found for: {title} (TMDB: {tmdb_id})")
                
                request_info = {
                    "id": request.get("id"),
                    "title": title,
                    "status": status,
                    "type": media_type,
                    "created_at": request.get("createdAt"),
                    "requested_by": request.get("requestedBy", {}).get("displayName", "Unknown"),
                    "tmdb_id": tmdb_id,
                    "poster_url": poster_url,
                    "backdrop_url": backdrop_url,
                    "overview": overview,
                    "release_date": release_date,
                    "genres": genres,
                    "rating": rating,
                    "runtime": runtime,
                    "media_info": media,  # Include raw media info for debugging
                }
                
                # Add to recent requests (first 5)
                if len(recent_requests) < 5:
                    recent_requests.append(request_info)
                
                # Add to status-specific lists (limit to 10 per status)
                if len(detailed_requests_by_status[status]) < 10:
                    detailed_requests_by_status[status].append(request_info)
            
            # Check for new pending requests
            current_pending_count = status_counts.get(1, 0)
            if current_pending_count > self._last_pending_count:
                # Fire event for new requests
                new_count = current_pending_count - self._last_pending_count
                self.hass.bus.async_fire(
                    f"{DOMAIN}_new_requests",
                    {
                        "count": new_count,
                        "requests": detailed_requests_by_status[1][:new_count]
                    }
                )
            self._last_pending_count = current_pending_count
            
            _LOGGER.info("Finished processing request data")
            
            return {
                "status_counts": status_counts,
                "total_requests": page_info.get("results", 0),
                "recent_requests": recent_requests,
                "detailed_requests": detailed_requests_by_status,
                "page_info": page_info,
                "raw_results": results,
            }
            
        except JellyseerrError as err:
            _LOGGER.error(f"Jellyseerr error: {str(err)}")
            raise UpdateFailed(str(err))
        except Exception as err:
            _LOGGER.error(f"Unexpected error: {str(err)}")
            raise UpdateFailed(f"Unexpected error: {err}")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jellyseerr from a config entry."""
    # Handle both lowercase and uppercase keys for compatibility
    host = entry.data.get(CONF_HOST) or entry.data.get("host")
    port = entry.data.get(CONF_PORT) or entry.data.get("port", DEFAULT_PORT)
    ssl = entry.data.get(CONF_SSL) or entry.data.get("ssl", DEFAULT_SSL)
    api_key = entry.data.get(CONF_API_KEY) or entry.data.get("api_key")
    
    if not host or not api_key:
        _LOGGER.error("Missing required configuration: host=%s, api_key=%s", bool(host), bool(api_key))
        return False

    _LOGGER.info(f"Setting up Jellyseerr: {host}:{port} SSL:{ssl}")

    session = async_get_clientsession(hass)
    api = JellyseerrAPI(session, host, port, ssl, api_key)

    # Test the connection
    try:
        if not await api.async_test_connection():
            raise ConfigEntryNotReady("Unable to connect to Jellyseerr")
    except JellyseerrAuthenticationError:
        _LOGGER.error("Invalid API key")
        return False
    except JellyseerrConnectionError as err:
        raise ConfigEntryNotReady(f"Connection error: {err}")

    coordinator = JellyseerrDataUpdateCoordinator(hass, api, entry)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    # Forward the setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def async_approve_request(call: ServiceCall):
        """Handle approve request service call."""
        request_id = call.data["request_id"]
        result = await api.async_approve_request(request_id)
        if result["success"]:
            # Trigger coordinator refresh to update status
            await coordinator.async_refresh()
        else:
            raise HomeAssistantError(f"Failed to approve request: {result.get('error', 'Unknown error')}")

    async def async_deny_request(call: ServiceCall):
        """Handle deny request service call."""
        request_id = call.data["request_id"]
        reason = call.data.get("reason", "Denied via Home Assistant")
        result = await api.async_deny_request(request_id, reason)
        if result["success"]:
            # Trigger coordinator refresh to update status
            await coordinator.async_refresh()
        else:
            raise HomeAssistantError(f"Failed to deny request: {result.get('error', 'Unknown error')}")

    async def async_batch_approve(call: ServiceCall):
        """Handle batch approve service call."""
        request_ids = call.data["request_ids"]
        results = []
        for request_id in request_ids:
            result = await api.async_approve_request(request_id)
            results.append({"id": request_id, "success": result["success"]})
            if result["success"]:
                await asyncio.sleep(0.5)  # Small delay between requests
        
        # Refresh after batch operation
        await coordinator.async_refresh()
        
        # Report results
        failed = [r["id"] for r in results if not r["success"]]
        if failed:
            raise HomeAssistantError(f"Failed to approve requests: {failed}")

    async def async_batch_deny(call: ServiceCall):
        """Handle batch deny service call."""
        request_ids = call.data["request_ids"]
        reason = call.data.get("reason", "Denied via Home Assistant")
        results = []
        for request_id in request_ids:
            result = await api.async_deny_request(request_id, reason)
            results.append({"id": request_id, "success": result["success"]})
            if result["success"]:
                await asyncio.sleep(0.5)  # Small delay between requests
        
        # Refresh after batch operation
        await coordinator.async_refresh()
        
        # Report results
        failed = [r["id"] for r in results if not r["success"]]
        if failed:
            raise HomeAssistantError(f"Failed to deny requests: {failed}")

    # Register the services
    hass.services.async_register(
        DOMAIN, SERVICE_APPROVE_REQUEST, async_approve_request, schema=APPROVE_REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DENY_REQUEST, async_deny_request, schema=DENY_REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_BATCH_APPROVE, async_batch_approve, schema=BATCH_APPROVE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_BATCH_DENY, async_batch_deny, schema=BATCH_DENY_SCHEMA
    )

    # Register device
    device_registry = dr.async_get(hass)
    server_info = await api.async_get_server_info()
    
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Jellyseerr",
        name=f"Jellyseerr ({host})",
        model="Jellyseerr Server",
        sw_version=server_info.get("version", "Unknown") if server_info else "Unknown",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove services only if no other instances
        if len([e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]) == 0:
            hass.services.async_remove(DOMAIN, SERVICE_APPROVE_REQUEST)
            hass.services.async_remove(DOMAIN, SERVICE_DENY_REQUEST)
            hass.services.async_remove(DOMAIN, SERVICE_BATCH_APPROVE)
            hass.services.async_remove(DOMAIN, SERVICE_BATCH_DENY)
        
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok