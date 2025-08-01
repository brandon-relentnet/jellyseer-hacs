"""Config flow for Jellyseerr integration."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from . import JellyseerrAPI, DOMAIN, DEFAULT_PORT, DEFAULT_SSL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): bool,
        vol.Required(CONF_API_KEY): str,
    }
)

# Options schema
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("update_interval", default=120): vol.All(
            cv.positive_int, vol.Range(min=30, max=3600)
        ),
        vol.Optional("fetch_size", default=50): vol.All(
            cv.positive_int, vol.Range(min=25, max=200)
        ),
        vol.Optional("trusted_users", default=[]): cv.ensure_list,
        vol.Optional("auto_approve_rating", default=7.5): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=10)
        ),
        vol.Optional("notification_on_new", default=True): bool,
        vol.Optional("notification_on_auto_approve", default=True): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    api = JellyseerrAPI(
        session,
        data[CONF_HOST],
        data[CONF_PORT],
        data[CONF_SSL],
        data[CONF_API_KEY],
    )

    # Test connection
    if not await api.async_test_connection():
        raise CannotConnect

    # Get server info for title
    server_info = await api.async_get_server_info()
    
    # Get some basic stats
    try:
        requests_data = await api.async_get_requests(take=1)
        total_requests = requests_data.get("pageInfo", {}).get("results", 0)
    except:
        total_requests = 0

    return {
        "title": f"Jellyseerr ({data[CONF_HOST]})",
        "server_version": server_info.get("version", "Unknown") if server_info else "Unknown",
        "total_requests": total_requests,
    }


class JellyseerrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jellyseerr."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            # Normalize host input
            host = user_input[CONF_HOST].strip()
            # Remove trailing slash if present
            if host.endswith("/"):
                host = host[:-1]
            user_input[CONF_HOST] = host
            
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", e)
                errors["base"] = "unknown"
            else:
                # Check if already configured
                existing_entry = await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                if existing_entry:
                    self._abort_if_unique_id_configured()
                
                # Show success info before creating entry
                self.context["server_info"] = info
                self.context["user_input"] = user_input
                return await self.async_step_confirm()

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/jellyfin/jellyseerr",
            }
        )

    async def async_step_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Confirm setup with server info."""
        if user_input is not None:
            # Get the original data from context
            data = self.context.get("user_input", {})
            info = self.context.get("server_info", {})
            # Ensure we use the correct constant keys
            config_data = {
                CONF_HOST: data.get(CONF_HOST),
                CONF_PORT: data.get(CONF_PORT, DEFAULT_PORT),
                CONF_SSL: data.get(CONF_SSL, DEFAULT_SSL),
                CONF_API_KEY: data.get(CONF_API_KEY),
            }
            return self.async_create_entry(title=info["title"], data=config_data)
        
        # Store user input for later
        if "user_input" not in self.context:
            self.context["user_input"] = self.context.get("data", {})
        
        info = self.context.get("server_info", {})
        
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "server_version": info.get("server_version", "Unknown"),
                "total_requests": info.get("total_requests", 0),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return JellyseerrOptionsFlowHandler(config_entry)


class JellyseerrOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Jellyseerr."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Process trusted users string into list
            if "trusted_users" in user_input:
                trusted_users_str = user_input["trusted_users"]
                if trusted_users_str:
                    user_input["trusted_users"] = [
                        user.strip() 
                        for user in trusted_users_str.split(",") 
                        if user.strip()
                    ]
                else:
                    user_input["trusted_users"] = []
            
            return self.async_create_entry(title="", data=user_input)

        # Get current values from config_entry available in self
        options = {
            "update_interval": self.config_entry.options.get("update_interval", 120),
            "fetch_size": self.config_entry.options.get("fetch_size", 50),
            "trusted_users": self.config_entry.options.get("trusted_users", []),
            "auto_approve_rating": self.config_entry.options.get("auto_approve_rating", 7.5),
            "notification_on_new": self.config_entry.options.get("notification_on_new", True),
            "notification_on_auto_approve": self.config_entry.options.get("notification_on_auto_approve", True),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "update_interval",
                        default=options["update_interval"],
                    ): vol.All(cv.positive_int, vol.Range(min=30, max=3600)),
                    vol.Optional(
                        "fetch_size",
                        default=options["fetch_size"],
                    ): vol.All(cv.positive_int, vol.Range(min=25, max=200)),
                    vol.Optional(
                        "trusted_users",
                        default=", ".join(options["trusted_users"]),
                    ): str,
                    vol.Optional(
                        "auto_approve_rating",
                        default=options["auto_approve_rating"],
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
                    vol.Optional(
                        "notification_on_new",
                        default=options["notification_on_new"],
                    ): bool,
                    vol.Optional(
                        "notification_on_auto_approve",
                        default=options["notification_on_auto_approve"],
                    ): bool,
                }
            ),
        )

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Process trusted users string into list
            if "trusted_users" in user_input:
                trusted_users_str = user_input["trusted_users"]
                if trusted_users_str:
                    user_input["trusted_users"] = [
                        user.strip() 
                        for user in trusted_users_str.split(",") 
                        if user.strip()
                    ]
                else:
                    user_input["trusted_users"] = []
            
            return self.async_create_entry(title="", data=user_input)

        # Get current values
        options = {
            "update_interval": self.config_entry.options.get("update_interval", 120),
            "fetch_size": self.config_entry.options.get("fetch_size", 50),
            "trusted_users": self.config_entry.options.get("trusted_users", []),
            "auto_approve_rating": self.config_entry.options.get("auto_approve_rating", 7.5),
            "notification_on_new": self.config_entry.options.get("notification_on_new", True),
            "notification_on_auto_approve": self.config_entry.options.get("notification_on_auto_approve", True),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "update_interval",
                        default=options["update_interval"],
                    ): vol.All(cv.positive_int, vol.Range(min=30, max=3600)),
                    vol.Optional(
                        "fetch_size",
                        default=options["fetch_size"],
                    ): vol.All(cv.positive_int, vol.Range(min=25, max=200)),
                    vol.Optional(
                        "trusted_users",
                        default=", ".join(options["trusted_users"]),
                        description={"suggested_value": ", ".join(options["trusted_users"])},
                    ): str,
                    vol.Optional(
                        "auto_approve_rating",
                        default=options["auto_approve_rating"],
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
                    vol.Optional(
                        "notification_on_new",
                        default=options["notification_on_new"],
                    ): bool,
                    vol.Optional(
                        "notification_on_auto_approve",
                        default=options["notification_on_auto_approve"],
                    ): bool,
                }
            ),
            description_placeholders={
                "current_interval": options["update_interval"],
                "current_fetch_size": options["fetch_size"],
            }
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""