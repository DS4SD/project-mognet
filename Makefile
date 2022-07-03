
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

.PHONY: lint
lint: lint-isort lint-black lint-pylint

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
