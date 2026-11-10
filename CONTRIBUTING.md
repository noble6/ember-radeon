# Contributing to Ember

Thanks for helping make Radeon on Linux better.

## The most valuable contributions
1. **Hardware reports.** Run Ember and paste **System → Copy report** plus `cat /sys/class/drm/card*/device/pp_od_clk_voltage` into an issue, especially for RDNA 4, Vega, Polaris, GCN 1–3 and APUs. Every new `pp_od_clk_voltage` format becomes a fixture in `tests/od_fixtures.py`.
2. **Display backends** for GNOME (Mutter D-Bus) and wlroots compositors. `ember/app/display.py` is the only file to extend.
3. **Translations and UI polish** in `qml/`.

## Rules for code that touches hardware
- Only `ember/daemon.py` writes to sysfs, and only values that came out of `ember/core/tuning.validate()`.
- Never allow voltage above stock. New controls get added to `od_controls()` with limits taken from `OD_RANGE`.
- Add a test with a fake sysfs tree (`tests/fakesys.py`) for every new write path.

## Releasing
1. Bump `__version__` in `ember/__init__.py` (and CITATION.cff, the metainfo and the PKGBUILD).
2. Commit and push, then run `packaging/make-release.sh`.
3. Create the GitHub release for tag `v<version>` and attach the three files from `dist/` (`.tar.gz`, `.sha256`, `.sig`). The built-in updater only installs releases whose tarball is signed with the release key. `make-release.sh` signs with the maintainer's private key (`~/.config/ember-release/signing-key.pem`), which is never committed or uploaded; forks that want self-updates replace `RELEASE_KEYS` in `ember/core/update.py` with their own public key.

## Running
```sh
python3 -m unittest discover tests
python3 main.py
```
Headless screenshots: `QT_QPA_PLATFORM=offscreen EMBER_SCREENSHOT=/tmp/shots python3 main.py`.
