Mo files update command using docker compose:

docker compose --profile dev run --rm migrate \
uv run --python python3 pybabel compile -d lms/translations