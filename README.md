# Beurer CosyNight Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/Bibbleq/HA-beurer-cosynight)

Home Assistant integration for Beurer CosyNight heated mattress cover with device grouping and comprehensive controls.

## Features

### Device Controls
- **Body Zone** - Control body zone heating intensity (0-9 levels)
- **Feet Zone** - Control feet zone heating intensity (0-9 levels)
- **Duration** - Set heating duration (30 min, 1-4 hours)
- **Remaining Time** - Sensor showing remaining heating time
- **Stop Button** - Instantly stop all heating

### Integration Benefits
- Add Beurer CosyNight devices via Home Assistant UI
- All entities grouped under a single device per blanket
- No YAML configuration required

## Installation

### HACS (Recommended)
1. Add this repository as a custom repository in HACS
2. Install the integration
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration**
5. Search for "Beurer CosyNight"
6. Enter your Beurer CosyNight account credentials

### Manual Installation
1. Copy the `custom_components/beurer_cosynight` folder to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant
3. Follow steps 4-6 above

## Configuration

Setup is done entirely through the Home Assistant GUI. No YAML configuration is required.

## Example Lovelace Card

See [beurer-card-example.yaml](beurer-card-example.yaml) for an example Lovelace card configuration.

## Credits & Attribution

This integration is a fork and derivative work, building upon the contributions of previous developers:

- **Original Author**: [Damon Kohler](https://github.com/damonkohler) - [home-assistant-beurer-cosynight](https://github.com/damonkohler/home-assistant-beurer-cosynight)

### What's New in v2.0.0
- Entities grouped under device (improved Home Assistant UI experience)
- Added Duration selector for heating time
- Added Remaining Time sensor
- Added Stop button for quick shutoff
- Config flow integration (no YAML required)
- Improved code structure and maintainability

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

This is a derivative work of the original [home-assistant-beurer-cosynight](https://github.com/damonkohler/home-assistant-beurer-cosynight) by Damon Kohler, also licensed under Apache License 2.0.
