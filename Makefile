
DOCKER_COMPOSE_FILE=.devcontainer/docker-compose.yaml

.PHONY: format-black
format-black:
	@poetry run black .

.PHONY: format-isort
format-isort:
	@poetry run isort .

.PHONY: format
format: format-isort format-black

.PHONY: lint-isort
lint-isort:
	@poetry run isort --check .

.PHONY: lint-black
lint-black:
	@poetry run black --check .

lint-pylint:
	@poetry run pylint mognet

lint-flake8:
	@poetry run flake8

lint-mypy:
	@poetry run mypy mognet

.PHONY: lint
lint: lint-isort lint-black lint-flake8 lint-pylint lint-mypy

.PHONY: docker-up
docker-up:
	@docker-compose \
		-f $(DOCKER_COMPOSE_FILE) \
		up -d

.PHONY: docker-down
docker-down:
	@docker-compose \
		-f $(DOCKER_COMPOSE_FILE) \
		down

.PHONY: test
test:
	@poetry run pytest test/
