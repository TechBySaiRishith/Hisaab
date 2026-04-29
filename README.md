# Badminton Splitter

Computes per-player badminton session costs (court + shuttle, slot-based) and generates `wa.me` payment-request links. Self-hosted on Raspberry Pi.

## Quickstart (development)

```bash
make install      # create venv, install deps, install pre-commit
make tailwind     # build CSS once
make dev          # run app at http://localhost:8080
```

## Deployment

See `docker/docker-compose.yml`. Use `make pi-deploy` from a workstation with SSH access to the Pi.

## Architecture

See `docs/superpowers/specs/2026-04-29-badminton-splitter-design.md`.
