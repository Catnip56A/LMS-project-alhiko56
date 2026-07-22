# Packages static/permanent/UI as a standalone image so it can be moved
# between machines via GHCR instead of git. Not part of the app image.
FROM scratch
COPY static/permanent/UI /assets
