# LTEK Trackers for Home Assistant

A Home Assistant integration that shows your LTEK GPS trackers: position on
the map, battery, speed, signal and whether each one is moving or online. It
covers every tracker your LTEK account can see, including the ones you own
and the ones other people have shared with you.

This version is read-only. It polls the LTEK API every 30 seconds with a
single request for the whole account. A tracker reports every 60 seconds
while it moves and every 5 minutes while it is parked, so polling more often
would not show anything new.

## Install

Copy `custom_components/ltek_trackers/` into the `custom_components/` folder
of your Home Assistant configuration directory, then restart Home Assistant.

HACS can only install from GitHub. This repository lives on GitLab, so HACS
will work once a GitHub mirror exists. Until then, install by copying the
folder as described above.

## Set up

1. Sign in on the LTEK website, open your profile page and create a
   **personal API token**. It starts with `ltk_` and is shown only once.
2. In Home Assistant go to *Settings → Devices & services → Add integration*
   and pick **LTEK Trackers**.
3. Choose the server and paste the token:

   | Server | URL | Use it for |
   |---|---|---|
   | Production | `https://api.ltek.dk` | Normal use |
   | Development | `https://api-dev.cluster.ltek.dk` | Testing new features |
   | Custom URL | your own | A self-hosted server. Must use https, except on `localhost` |

**Each token works on one server only.** A production token does not work on
development, and a development token does not work on production. To see both,
add the integration twice, once per server, each with a token created on that
server's website. The development entry gets " (dev)" added to its title.

If a token is revoked or expires, Home Assistant asks for a new one. The new
token must belong to the same account. To move an entry to another server or
account, open the entry's menu and choose *Reconfigure*.

## What you get

Each tracker becomes a device, named as it is on the LTEK website. If a
tracker is unshared, its share expires or it is released, its device is
removed on the next poll. If it is shared again, the device is added back.

| Entity | Notes |
|---|---|
| Location (`device_tracker`) | GPS position, accuracy and battery. Works with zones, person entities and the map card |
| Battery | Percentage |
| Speed | Shown in km/h |
| Altitude | Metres |
| Last seen | Time of the newest message from the tracker |
| Moving | On while the tracker reports that it is moving |
| Online | Whether the tracker is reporting on schedule |
| Signal strength (RSRP) | Diagnostic |
| Firmware | Diagnostic |
| Configuration state | Diagnostic. Shown only when you can change the tracker's settings (manager or owner) |
| Battery voltage, satellites, signal-to-noise ratio, modem firmware | Diagnostic, disabled by default |

When the server leaves out a value, for example a tracker that has no GPS
fix yet, that entity shows *unknown*.

## Privacy

The token gives access to the same trackers your account sees on the LTEK
website, with the same limits. Anyone who holds the token can see where those
trackers are. Keep the token in Home Assistant only. Do not put it in
`secrets.yaml`, scripts or anywhere else, and revoke it on your profile page if
it leaks. A shared tracker shows only what its owner has shared with you. If
the share has an end date, the tracker disappears from Home Assistant when
the share ends.

The diagnostics download removes the token and all coordinates.

## Development

```bash
uv venv
uv pip install --group dev
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest
```

The tests use `pytest-homeassistant-custom-component` against recorded,
made-up API responses. They never contact a real server.
