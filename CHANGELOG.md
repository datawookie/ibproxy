# Change Log

## [0.0.6] - 2025-08-24

- Rename module from `proxy` to `ibproxy`.

## [0.0.5] - 2025-08-23

- Improve test coverage to 86.9%.
- Add /health endpoint.
- Neaten logging.

## [0.0.4] - 2025-08-22

- Request and response data dumped as compressed JSON under `journal/`.
- Journal files partitioned by date.
- Record duration of API call. Log and add as field in journal file.
