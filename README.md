# gridyard for Home Assistant

Home Assistant integration for gridyard devices. It reads the device in your home network, without a gridyard
account and without the gridyard cloud.

**Status:** in development, not ready for use.

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
