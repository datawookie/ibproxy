# Change Log

## [0.1.2] - 2025-09-26

- Update to ibauth v0.1.1.
- Add `--tickle-interval` CLI argument.
- Refactor tickle.

## [0.1.1] - 2025-09-24

## [0.1.0] - 2025-09-19

- Update to `ibauth` v0.1.0 (fully async).
- Increase tickle interval to 2 minutes.
- Sleep before tickle.
- Add MIT license.

## [0.0.16] - 2025-09-13

- Update to `ibauth` v0.0.11.
- Journal filename embeds request ID.

## [0.0.15] - 2025-09-12

- Add unique request ID.
- Create separate module for `tickle_loop()`.

## [0.0.14] - 2025-09-10

- Add timeout on call to `get_system_status()`.
- More robust implementation of tickle loop.
- Update to `ibauth` v0.0.9.

## [0.0.13] - 2025-09-07

- Get IBKR status.

## [0.0.12] - 2025-09-01

- Add --tickle-mode option, which can be 'off', 'auto' or 'always'.

## [0.0.11] - 2025-08-30

- Write JSON journal data in a thread so that it doesn't block.
- Update to `ibauth` v0.0.7.
- Simplified authentication workflow.

## [0.0.10] - 2025-08-25

- Add failed requests as journal JSON.

## [0.0.9] - 2025-08-25

- Include parameters in journal JSON.

## [0.0.8] - 2025-08-25

- Change tickle interval to 60 s.
- Don't tickle immediately if there has been a recent API request.

## [0.0.7] - 2025-08-25

- Update to `ibauth` v0.0.6.

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
