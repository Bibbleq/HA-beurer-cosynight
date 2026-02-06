"""Constants for the Beurer CosyNight integration."""

DOMAIN = "beurer_cosynight"

# Configuration options for polling
CONF_PEAK_HOURS_START = "peak_hours_start"
CONF_PEAK_HOURS_END = "peak_hours_end"
CONF_OFFPEAK_INTERVAL_MINUTES = "offpeak_interval_minutes"
CONF_PEAK_INTERVAL_MINUTES = "peak_interval_minutes"
CONF_ACTIVE_BLANKET_ENABLED = "active_blanket_enabled"

# Default values
DEFAULT_PEAK_HOURS_START = "20:00"
DEFAULT_PEAK_HOURS_END = "08:00"
DEFAULT_OFFPEAK_INTERVAL_MINUTES = 10
DEFAULT_PEAK_INTERVAL_MINUTES = 5
DEFAULT_ACTIVE_BLANKET_ENABLED = True