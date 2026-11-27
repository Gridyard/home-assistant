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

## Development

Requires Python 3.14.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check
.venv/bin/ruff format --check
.venv/bin/pytest
```

## License

[Apache-2.0](LICENSE)
