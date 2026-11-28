# gridyard for Home Assistant

Home Assistant integration for the [gridyard](https://gridyard.de) reader, a reading head for your meter. Home
Assistant reads the device in your home network, without a gridyard account and without the gridyard cloud.

**Status:** in development, not ready for use. The integration needs device firmware with the local API, which is
not released yet. The gridyard app and the firmware will add the setup paths below in later releases.

## Requirements

- Home Assistant 2026.10 or later
- a gridyard reader with firmware that offers the local API, in mode *Local* or *Cloud and local*
- Home Assistant and the device in the same network, or the device reachable from Home Assistant by its IP address

## Installation

Install with [HACS](https://www.hacs.xyz/):

1. Add `https://github.com/Gridyard/home-assistant` to HACS as a custom repository of type *Integration*.
2. Download *gridyard* in HACS.
3. Restart Home Assistant.

Without HACS, copy `custom_components/gridyard` into the `custom_components` folder of your Home Assistant
configuration and restart Home Assistant.

## Setup

### 1. Put the device on your Wi-Fi

| Way | How | Mode | Available |
| --- | --- | --- | --- |
| gridyard app without an account | *Set up without an account (Home Assistant)* on the sign-in screen: scan the label, choose the meter, choose the Wi-Fi | Local | with a later app release |
| Home Assistant only | with the WPS button of your router; Home Assistant then finds the device | Local | with a later firmware release |
| gridyard app with an account | during setup, switch on *Also local for Home Assistant* | Cloud and local | with a later app release |

In mode *Local* the device sends nothing to gridyard. In mode *Cloud and local* it keeps sending readings to your
gridyard account, and Home Assistant reads the same values locally.

### 2. Add the device in Home Assistant

1. Home Assistant finds the device on your network and shows it under **Settings → Devices & services**. Select
   **Add**. If it does not appear, add the integration *gridyard* and enter the IP address or host name of the
   device.
2. Enter the 12-character setup code from the label of the device.
3. If the device has no meter profile yet, choose your meter. Encrypted meters also need the 32-character meter key
   from your grid operator. The device restarts and Home Assistant waits up to a minute for the new profile.

## What you get

- **Sensors** for each value the meter profile provides: energy, power, voltage, current and more, per tariff and
  phase where the meter reports them.
- **Diagnostic sensors:** *Meter* (state of the meter connection), *Data quality*, *Mode*, *Meter profile* and
  *Wi-Fi signal* (disabled by default).
- **Firmware update** entity, see [Firmware updates](#firmware-updates).
- **Diagnostics download** without host, setup code, meter key or readings; the device ID is shortened.

Home Assistant reads the device every 5 seconds. When the meter delivers no usable data, the value sensors become
unavailable; the diagnostic sensors say why.

### Energy dashboard

*Energy import* and *Energy export* are meter readings in kWh. In the energy dashboard settings, add *Energy import*
as grid consumption and *Energy export* as return to grid. Prices are set there too; the integration has no tariff
settings of its own.

### evcc

[evcc](https://evcc.io) uses the device as its grid meter through Home Assistant, with the *Home Assistant* meter of
evcc ([documentation](https://docs.evcc.io/en/smarthome/home-assistant), evcc 0.319.1):

1. In evcc under **Configuration**, add the grid meter and choose *Home Assistant* as the manufacturer.
2. Choose your Home Assistant instance and authorise evcc; Home Assistant opens its login page for that. If evcc
   runs as an app in Home Assistant, choose `http://supervisor/core`; it is authorised already.
3. Assign the sensors of the device, then select **Validate & save**:

| evcc field | Sensor |
| --- | --- |
| Power Entity | *Power* |
| Energy Entity | *Energy import* |
| Return Energy Entity | *Energy export* |
| L1–L3 Current Entity, L1–L3 Voltage Entity (optional) | *Current L1* to *L3*, *Voltage L1* to *L3* |

*Power* is positive for import from the grid and negative for export, as evcc expects of a grid meter. If your meter
reports only *Power import* and *Power export*, create a template sensor helper in Home Assistant with the unit W and
the following state, and assign it as *Power Entity*. While a sensor is unavailable, the helper stays unknown
instead of reporting a wrong value:

```jinja
{{ (states('sensor.sm_xxxxxx_power_import') | float - states('sensor.sm_xxxxxx_power_export') | float)
   if has_value('sensor.sm_xxxxxx_power_import') and has_value('sensor.sm_xxxxxx_power_export') else none }}
```

### Options

Under **Configure** on the integration entry you can change the meter profile, set a new meter key and switch the
firmware update check on or off. Profile and key are stored on the device; changing them restarts it.

## Firmware updates

The integration reads `manifest.json` of the latest release in
[Gridyard/firmware](https://github.com/Gridyard/firmware) every 6 hours and offers new firmware as an update. It
downloads the image, checks its size and SHA-256, sends it to the device and waits until the device confirms the
new version after a trial boot. If the trial boot fails, the device runs the previous version again and Home
Assistant says so. GitHub sees the address of your Home Assistant server. Switch the check off in the options of
the integration; then no request goes to GitHub.

## Privacy

- In mode *Local* the device connects to nothing outside your network, and neither the integration nor the
  gridyard app without an account sends anything to gridyard.
- The integration collects no telemetry. Its only request outside your network is the firmware update check at
  GitHub, which you can switch off.

## Security

- The integration and the device talk over an encrypted session (ESP-IDF Security 2) that needs the setup code.
  Without the code, nobody in your network can read or change the device.
- The setup code on the label is permanent and cannot be changed. Anyone who knows it, for example a flatmate or a
  previous owner, can read the values and change the meter profile from inside your Wi-Fi. Keep the label private.
  If you give the device away or get it second-hand, factory reset it and put it on a Wi-Fi the previous owner
  cannot reach.
- Home Assistant stores the host and the setup code in plain text in its configuration directory
  (`.storage/core.config_entries`), like the credentials of other integrations. Anyone who can read that directory
  can connect to the device in your home network.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The device is not found | Discovery uses mDNS, which does not cross VLANs or subnets. Add the integration by hand with the IP address of the device, and give the device a fixed address in your router |
| *The device rejected the setup code* | Check the code on the label: 12 characters, no I, L, O or U. After a wrong code the device refuses connections for up to 300 seconds, so *Failed to connect* can follow; wait and try again |
| *The firmware of the device does not support Home Assistant yet* | Update the firmware of the device |
| Sensors become unavailable | Check the diagnostic sensor *Meter*. The local API is off in mode *Cloud* and while the setup window of the device is open |

### Known limitations

- The device accepts one client at a time. Another tool that connects to it, for example `esp_prov`, closes the
  session of Home Assistant.
- The Wi-Fi of the device cannot be changed from Home Assistant; use WPS or the gridyard app.
- The polling interval is fixed at 5 seconds.

## Removal

Delete the integration entry under **Settings → Devices & services → gridyard**, then remove *gridyard* in HACS.
The device keeps running in its mode. To take it off your network or to hand it on, factory reset it: hold its
button for at least 12 seconds, release it, then press it briefly within 5 seconds.

## Development

Requires Python 3.14.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check
.venv/bin/ruff format --check
.venv/bin/pytest
```

To test firmware updates against a release server of your own, set `GRIDYARD_MANIFEST_URL` to its `manifest.json`
in the environment of Home Assistant.

## License

[Apache-2.0](LICENSE)
