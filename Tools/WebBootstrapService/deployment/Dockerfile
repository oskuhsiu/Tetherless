# Build context: repository root. Official versioned images; record resolved image
# digests when building. Debian package versions are recorded by CI, not pinned.
FROM node:24.19.0-trixie-slim@sha256:ab3eebe934147fee049b5eb83c570f68c849a13c930bdfa482de99fcdfa3b3de AS frontend
ARG SOURCE_COMMIT
RUN node -e "if (!/^[a-f0-9]{40}$/.test(process.env.SOURCE_COMMIT || '')) process.exit(1)"
WORKDIR /src/WebBootstrap
COPY WebBootstrap/package.json WebBootstrap/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY WebBootstrap/ ./
RUN npm test && npm run build \
    && mkdir -p /build-info \
    && node --version > /build-info/frontend-node.txt \
    && npm --version > /build-info/frontend-npm.txt \
    && dpkg-query -W > /build-info/frontend-debian-packages.txt

FROM rust:1.99.0-trixie@sha256:15ad267e7a4cb2dce5905c90c76765adb6714945c5ea6d7c82673897a5e4067b AS backend
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src/Tools/WebBootstrapService
COPY Tools/WebBootstrapService/Cargo.toml Tools/WebBootstrapService/Cargo.lock ./
COPY Tools/WebBootstrapService/src/ ./src/
COPY Tools/WebBootstrapService/tests/ ./tests/
RUN cargo test --locked --all-targets && cargo build --locked --release \
    && mkdir -p /build-info \
    && rustc --version > /build-info/backend-rustc.txt \
    && cargo --version > /build-info/backend-cargo.txt \
    && dpkg-query -W > /build-info/backend-debian-packages.txt

FROM node:24.19.0-trixie-slim@sha256:ab3eebe934147fee049b5eb83c570f68c849a13c930bdfa482de99fcdfa3b3de AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libssl3t64 libgcc-s1 zlib1g libzstd1 \
    && rm -rf /var/lib/apt/lists/*
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT
WORKDIR /app
COPY --from=backend /src/Tools/WebBootstrapService/target/release/tetherless-web-bootstrap-service /app/
COPY --from=frontend /src/WebBootstrap/dist /app/frontend
COPY --from=frontend /build-info /app/build-info
COPY --from=backend /build-info /app/build-info
COPY LICENSE /app/licenses/AGPL-3.0.txt
COPY Tools/WebBootstrapService/README.md /app/licenses/account-service-notices.md
COPY Tools/WebBootstrapService/deployment/*.mjs /app/deployment/
RUN node -e "if (!/^[a-f0-9]{40}$/.test(process.env.SOURCE_COMMIT || '')) process.exit(1)" \
    && printf '%s\n' "$SOURCE_COMMIT" > /app/build-info/source-commit.txt \
    && dpkg-query -W > /app/build-info/runtime-debian-packages.txt \
    && chmod 0555 /app/tetherless-web-bootstrap-service \
    && chmod -R a-w /app
ENV NODE_ENV=production PORT=10000 TETHERLESS_FRONTEND_DIR=/app/frontend
USER node
EXPOSE 10000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["node", "/app/deployment/healthcheck.mjs"]
CMD ["node", "/app/deployment/entrypoint.mjs"]
