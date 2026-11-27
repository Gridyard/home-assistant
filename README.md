# gridyard for Home Assistant

Home Assistant integration for gridyard devices. It reads the device in your home network, without a gridyard
account and without the gridyard cloud.

**Status:** in development, not ready for use.

## Setup

Add the integration, enter the IP address or host name of the device, then the 12-character setup code from its
label. Home Assistant checks the code with an encrypted session and polls the device every 5 seconds.

Home Assistant stores the host and the setup code in plain text in its configuration directory
(`.storage/core.config_entries`), like the credentials of other integrations. Anyone who can read that directory can
connect to the device in your home network.

## Firmware updates

The integration reads `manifest.json` of the latest release in
[Gridyard/firmware](https://github.com/Gridyard/firmware) every 6 hours and offers new firmware as an update. It
downloads the image, checks its size and SHA-256, sends it to the device and waits until the device confirms the
new version after a trial boot. If the trial boot fails, the device runs the previous version again and Home
Assistant says so. GitHub sees the address of your Home Assistant server. Switch the check off in the options of
the integration; then no request goes to GitHub.

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
