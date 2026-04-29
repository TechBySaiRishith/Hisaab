.PHONY: install dev tailwind tailwind-watch lint type ci clean docker-build pi-deploy pi-bootstrap

PI_HOST ?= pi
PI_PATH ?= /opt/hisaab

install:
	python -m venv .venv
	.venv/Scripts/pip install -e ".[dev]"
	.venv/Scripts/pre-commit install

dev:
	.venv/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

tailwind:
	tailwindcss -i app/web/static/css/tailwind.input.css -o app/web/static/css/tailwind.output.css --minify

tailwind-watch:
	tailwindcss -i app/web/static/css/tailwind.input.css -o app/web/static/css/tailwind.output.css --watch

lint:
	.venv/Scripts/ruff check .
	.venv/Scripts/ruff format --check .

type:
	.venv/Scripts/mypy app/domain app/services

ci: lint type

clean:
	rm -rf .mypy_cache .ruff_cache dist build
	find . -name __pycache__ -type d -exec rm -rf {} +

docker-build:
	docker buildx build --platform linux/arm64 -t hisaab:latest -f docker/Dockerfile .

pi-deploy:
	@test -n "$(GITHUB_OWNER)" || (echo "set GITHUB_OWNER" && exit 1)
	ssh $(PI_HOST) "cd $(PI_PATH) && \
		sed -i 's|{{GITHUB_OWNER}}|$(GITHUB_OWNER)|g' docker-compose.yml && \
		docker compose pull && \
		docker compose up -d && \
		sleep 5 && \
		curl -fs http://localhost:8080/health"

pi-bootstrap:
	@test -n "$(PI_HOST)" || (echo "set PI_HOST" && exit 1)
	ssh $(PI_HOST) "sudo mkdir -p $(PI_PATH)/data $(PI_PATH)/backup"
	scp docker/docker-compose.yml docker/litestream.yml $(PI_HOST):$(PI_PATH)/
