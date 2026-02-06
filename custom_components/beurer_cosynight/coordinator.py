"""DataUpdateCoordinator for Beurer CosyNight integration."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_PEAK_HOURS_START,
    CONF_PEAK_HOURS_END,
    CONF_OFFPEAK_INTERVAL_MINUTES,
    CONF_PEAK_INTERVAL_MINUTES,
    CONF_ACTIVE_BLANKET_ENABLED,
    DEFAULT_PEAK_HOURS_START,
    DEFAULT_PEAK_HOURS_END,
    DEFAULT_OFFPEAK_INTERVAL_MINUTES,
    DEFAULT_PEAK_INTERVAL_MINUTES,
    DEFAULT_ACTIVE_BLANKET_ENABLED,
)

_LOGGER = logging.getLogger(__name__)


class BeurerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Beurer CosyNight data."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub,
        devices: list,
        config_entry,
    ) -> None:
        """Initialize the coordinator."""
        self.hub = hub
        self.devices = devices
        self.config_entry = config_entry
        
        # Track when commands are sent to trigger aggressive polling
        self._last_command_time: datetime | None = None
        self._active_polling_enabled = False
        
        # Get configuration options with defaults
        options = config_entry.options if config_entry.options else {}
        self.peak_hours_start = self._parse_time(
            options.get(CONF_PEAK_HOURS_START, DEFAULT_PEAK_HOURS_START)
        )
        self.peak_hours_end = self._parse_time(
            options.get(CONF_PEAK_HOURS_END, DEFAULT_PEAK_HOURS_END)
        )
        self.offpeak_interval_minutes = options.get(
            CONF_OFFPEAK_INTERVAL_MINUTES, DEFAULT_OFFPEAK_INTERVAL_MINUTES
        )
        self.peak_interval_minutes = options.get(
            CONF_PEAK_INTERVAL_MINUTES, DEFAULT_PEAK_INTERVAL_MINUTES
        )
        self.active_blanket_enabled = options.get(
            CONF_ACTIVE_BLANKET_ENABLED, DEFAULT_ACTIVE_BLANKET_ENABLED
        )
        
        # Initialize with off-peak interval
        initial_interval = timedelta(minutes=self.offpeak_interval_minutes)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=initial_interval,
        )

    def _parse_time(self, time_str: str) -> time:
        """Parse time string in HH:MM format."""
        try:
            hours, minutes = time_str.split(":")
            return time(int(hours), int(minutes))
        except (ValueError, AttributeError):
            _LOGGER.error("Invalid time format: %s, using default", time_str)
            return time(20, 0)  # Default to 8pm

    def _is_in_peak_hours(self, current_time: time) -> bool:
        """Check if current time is within peak hours."""
        start = self.peak_hours_start
        end = self.peak_hours_end
        
        # Handle overnight ranges (e.g., 20:00 to 08:00)
        if start > end:
            return current_time >= start or current_time < end
        else:
            # Same-day range (e.g., 09:00 to 17:00)
            return start <= current_time < end

    def _is_blanket_active(self, device_status) -> bool:
        """Check if blanket is actively heating."""
        if not device_status:
            return False
        
        # Check if timer is running or any zone is heating
        return (
            device_status.timer > 0
            or device_status.bodySetting > 0
            or device_status.feetSetting > 0
        )

    def _get_progressive_active_interval(self) -> timedelta:
        """Get progressive interval for active blanket polling."""
        if not self._last_command_time:
            return timedelta(seconds=60)
        
        time_since_command = datetime.now() - self._last_command_time
        
        # Progressive intervals: 15s (first minute) → 30s (1-5 minutes) → 60s (after 5 minutes)
        if time_since_command < timedelta(minutes=1):
            return timedelta(seconds=15)
        elif time_since_command < timedelta(minutes=5):
            return timedelta(seconds=30)
        else:
            return timedelta(seconds=60)

    def _calculate_update_interval(self) -> timedelta:
        """Calculate the appropriate update interval based on current state."""
        now = datetime.now()
        current_time = now.time()
        
        # Check if any blanket is active
        any_active = False
        if self.data:
            for device_id, status in self.data.items():
                if self._is_blanket_active(status):
                    any_active = True
                    break
        
        # Tier 3: Active blanket polling (if enabled)
        if any_active and self.active_blanket_enabled:
            if not self._active_polling_enabled:
                _LOGGER.debug("Entering active blanket polling mode")
                self._active_polling_enabled = True
            interval = self._get_progressive_active_interval()
            _LOGGER.debug("Active blanket detected, using %s interval", interval)
            return interval
        
        # Reset active polling state if blanket is no longer active
        if self._active_polling_enabled and not any_active:
            _LOGGER.debug("Blanket inactive, returning to time-based polling")
            self._active_polling_enabled = False
            self._last_command_time = None
        
        # Tier 2: Peak hours
        if self._is_in_peak_hours(current_time):
            interval = timedelta(minutes=self.peak_interval_minutes)
            _LOGGER.debug("Peak hours detected, using %s interval", interval)
            return interval
        
        # Tier 1: Off-peak hours (default)
        interval = timedelta(minutes=self.offpeak_interval_minutes)
        _LOGGER.debug("Off-peak hours, using %s interval", interval)
        return interval

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        data = {}
        
        for device in self.devices:
            try:
                # Call get_status for each device
                status = await self.hass.async_add_executor_job(
                    self.hub.get_status, device.id
                )
                data[device.id] = status
            except Exception as err:
                _LOGGER.error(
                    "Error fetching data for device %s: %s",
                    device.id,
                    err,
                )
                # Keep old data if available, otherwise mark as unavailable
                if self.data and device.id in self.data:
                    data[device.id] = self.data[device.id]
                else:
                    raise UpdateFailed(f"Error fetching data for device {device.id}: {err}")
        
        # After successful update, recalculate interval for next update
        new_interval = self._calculate_update_interval()
        if new_interval != self.update_interval:
            _LOGGER.debug(
                "Updating coordinator interval from %s to %s",
                self.update_interval,
                new_interval,
            )
            self.update_interval = new_interval
        
        return data

    def notify_command_sent(self) -> None:
        """Notify coordinator that a command was sent to trigger active polling."""
        self._last_command_time = datetime.now()
        _LOGGER.debug("Command sent, triggering active polling mode")
        
        # Force an immediate update to get fresh status
        self.hass.async_create_task(self.async_request_refresh())
