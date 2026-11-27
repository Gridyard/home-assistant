# Changelog

All notable changes to this integration. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Setup by host and setup code; Home Assistant checks the code over an encrypted session.
- Discovery over mDNS (zeroconf), and a new request for the setup code when the device rejects the stored one.
- Meter profile and meter key in setup and options.
- Sensors for the values of the meter profile, per tariff and phase; diagnostic sensors for meter state, data
  quality, mode, meter profile and Wi-Fi signal.
- Firmware update entity with a check of the releases in Gridyard/firmware, which can be switched off.
- Diagnostics download without host, setup code, meter key or readings.
