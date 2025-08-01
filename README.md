# Jellyseerr Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/brandon-relentnet/jellyseerr-hacs.svg?style=flat-square)](https://github.com/brandon-relentnet/jellyseerr-hacs/releases)
[![License](https://img.shields.io/github/license/brandon-relentnet/jellyseerr-hacs.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration that allows you to monitor and manage [Jellyseerr](https://github.com/Fallenbagel/jellyseerr) media requests directly from your Home Assistant instance.

## Features

- **Real-time monitoring** of media request statuses (pending, approved, processing, available)
- **Approve or deny requests** directly from Home Assistant
- **Batch operations** for managing multiple requests at once
- **Auto-approval switches** with configurable criteria:
  - Auto-approve all requests
  - Auto-approve high-rated content (8+ rating)
  - Auto-approve requests from trusted users
- **Custom Lovelace card** with poster images and action buttons
- **Event triggers** for automation when new requests arrive
- **TMDB integration** for enhanced media metadata

## Prerequisites

- Home Assistant 2024.1.0 or newer
- Jellyseerr instance with API access
- Jellyseerr API key (found in Jellyseerr Settings → General → API Key)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/brandon-relentnet/jellyseerr-hacs`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Jellyseerr" and install it
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/brandon-relentnet/jellyseerr-hacs/releases)
2. Extract the `jellyseerr` folder to your `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Jellyseerr"
4. Enter your Jellyseerr server details:
   - **Host**: Your Jellyseerr server address (e.g., `192.168.1.100` or `jellyseerr.example.com`)
   - **Port**: Default is 5055
   - **Use SSL**: Enable if using HTTPS
   - **API Key**: Your Jellyseerr API key

### Configuration Options

After initial setup, you can configure:
- **Update interval**: How often to fetch new data (30-3600 seconds, default: 120)
- **Request fetch size**: Number of requests to fetch (25-200, default: 50)

## Entities

### Sensors
- `sensor.jellyseerr_pending_requests` - Count of pending requests
- `sensor.jellyseerr_approved_requests` - Count of approved requests
- `sensor.jellyseerr_processing_requests` - Count of processing requests
- `sensor.jellyseerr_available_requests` - Count of available requests

Each sensor includes detailed attributes with the full request data.

### Buttons
- `button.jellyseerr_refresh` - Manually refresh all data
- `button.jellyseerr_approve_all_pending` - Approve all pending requests
- `button.jellyseerr_approve_high_rated` - Approve pending requests with 8+ rating

### Switches
- `switch.jellyseerr_auto_approve` - Automatically approve all new requests
- `switch.jellyseerr_auto_approve_high_rated` - Automatically approve high-rated requests
- `switch.jellyseerr_auto_approve_trusted_users` - Automatically approve requests from trusted users

## Services

### jellyseerr.approve_request
Approve a single media request.

```yaml
service: jellyseerr.approve_request
data:
  request_id: 123
```

### jellyseerr.deny_request
Deny a single media request with an optional reason.

```yaml
service: jellyseerr.deny_request
data:
  request_id: 123
  reason: "Not available in our region"  # Optional
```

### jellyseerr.batch_approve
Approve multiple requests at once.

```yaml
service: jellyseerr.batch_approve
data:
  request_ids: [123, 456, 789]
```

### jellyseerr.batch_deny
Deny multiple requests at once.

```yaml
service: jellyseerr.batch_deny
data:
  request_ids: [123, 456, 789]
  reason: "Duplicate requests"  # Optional
```

## Custom Lovelace Card

This integration includes a custom card for displaying requests with poster images.

### Installation

1. The `jellyseerr-requests-card.js` file is automatically installed in the correct location
2. Add it as a resource in your Lovelace configuration:
   ```yaml
   resources:
     - url: /local/jellyseerr-requests-card.js
       type: module
   ```

### Usage

```yaml
type: custom:jellyseerr-requests-card
entity: sensor.jellyseerr_pending_requests
title: Pending Media Requests
show_title: true
show_status: true
max_requests: 10
```

See the included `example_dashboard.yaml` for a complete dashboard configuration.

## Automations

### Example: Notify on New Request

```yaml
automation:
  - alias: "Notify on New Jellyseerr Request"
    trigger:
      - platform: event
        event_type: jellyseerr_new_request
    action:
      - service: notify.mobile_app
        data:
          title: "New Media Request"
          message: "{{ trigger.event.data.media_type }} request from {{ trigger.event.data.requested_by }}"
```

### Example: Auto-approve trusted users

```yaml
automation:
  - alias: "Auto-approve trusted user requests"
    trigger:
      - platform: event
        event_type: jellyseerr_new_request
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.requested_by in ['user1', 'user2'] }}"
    action:
      - service: jellyseerr.approve_request
        data:
          request_id: "{{ trigger.event.data.request_id }}"
```

## Troubleshooting

### Connection Issues
- Ensure your Jellyseerr server is accessible from Home Assistant
- Check that the API key is correct
- If using a reverse proxy, make sure the host includes the full path

### Missing Data
- Check the Home Assistant logs for any errors
- Verify your Jellyseerr instance is running
- Try increasing the update interval if you're hitting rate limits

## Support

- [Report issues](https://github.com/brandon-relentnet/jellyseerr-hacs/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.