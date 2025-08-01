# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is a Home Assistant custom integration for Jellyseerr, a media request management system. The integration allows Home Assistant to monitor, display, and manage Jellyseerr requests through sensors, buttons, and switches.

## Architecture
- **Main Integration** (`__init__.py`): Contains the core `JellyseerrAPI` class and `JellyseerrDataUpdateCoordinator` for data fetching
- **Config Flow** (`config_flow.py`): Handles setup and configuration of the integration
- **Platform Files**:
  - `sensor.py`: Status sensors for different request states (pending, approved, processing, available)
  - `button.py`: Action buttons for refresh and bulk operations
  - `switch.py`: Auto-approval switches with different criteria

## Key Components

### JellyseerrAPI Class
- Handles all API communication with Jellyseerr server
- Smart URL construction for reverse proxy scenarios
- Supports approve/deny operations and batch operations
- Fetches media details from TMDB for enhanced metadata
- Located in `__init__.py:67-269`

### Data Coordinator
- Fetches request data every 2 minutes (configurable)
- Processes and enriches request data with TMDB metadata
- Manages request status counts and detailed request lists
- Fires events for new requests to trigger automation
- Located in `__init__.py:271-441`

### Services
The integration provides these Home Assistant services:
- `jellyseerr.approve_request`: Approve a single request
- `jellyseerr.deny_request`: Deny a single request with optional reason
- `jellyseerr.batch_approve`: Approve multiple requests
- `jellyseerr.batch_deny`: Deny multiple requests

### Request Status Mapping
- Status 1: Pending
- Status 2: Approved
- Status 3: Partially Available
- Status 4: Processing
- Status 5: Available

## Custom Frontend Card
Includes a custom Lovelace card (`jellyseerr-requests-card.js`) for displaying requests with poster images and action buttons in the Home Assistant UI.

## Development Notes
- No build, test, or lint commands are present in this repository
- This is a standalone Home Assistant custom integration
- Uses Home Assistant's configuration flow pattern for setup
- Implements proper device registry integration
- All API calls include proper error handling and timeout management
- Uses `aiohttp` for async HTTP requests
- Configuration validation with `voluptuous`
- Follows Home Assistant's async/await patterns