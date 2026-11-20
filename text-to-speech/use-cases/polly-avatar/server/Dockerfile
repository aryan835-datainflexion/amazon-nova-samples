# Multi-stage build for the Polly Avatar WebSocket server.
# Build context is the REPO ROOT (needs both server/ and shared/).
#
#   docker build -f server/Dockerfile -t polly-avatar-server .

# ---- build stage ----
FROM public.ecr.aws/docker/library/node:22-alpine AS build

# CACHE_BUST invalidates the package-upgrade layer so a rebuild re-fetches the
# latest OS packages instead of reusing a stale cached layer. The deploy passes
# a fresh timestamp (see CDK asset buildArgs), guaranteeing current packages.
ARG CACHE_BUST=unset

# Patch OS packages to the latest available versions (picks up security fixes
# like openssl) so the build isn't stuck on whatever shipped in the base image.
RUN echo "cache-bust: $CACHE_BUST" && apk update && apk upgrade --no-cache

WORKDIR /app

# Install deps first (better layer caching).
COPY server/package.json server/package-lock.json* ./server/
WORKDIR /app/server
RUN npm ci

# Copy sources (server + shared types it imports).
WORKDIR /app
COPY server/tsconfig.json ./server/
COPY server/src ./server/src
COPY shared ./shared

WORKDIR /app/server
RUN npm run build

# ---- runtime stage ----
FROM public.ecr.aws/docker/library/node:22-alpine AS runtime

# Same cache-bust for the runtime image — this is what actually ships, so
# keeping it current on security fixes (openssl, etc.) matters most here.
ARG CACHE_BUST=unset

RUN echo "cache-bust: $CACHE_BUST" && apk update && apk upgrade --no-cache

WORKDIR /app/server
ENV NODE_ENV=production

# Only production deps in the final image.
COPY server/package.json server/package-lock.json* ./
RUN npm ci --omit=dev && npm cache clean --force

# Compiled output (tsconfig rootDir is "..", so dist mirrors server/ + shared/).
COPY --from=build /app/server/dist ./dist

# Run as non-root.
RUN addgroup -S app && adduser -S app -G app
USER app

EXPOSE 8080
# Container-level health check (same /health endpoint the ALB target group uses).
# busybox wget ships with the alpine base image, so no extra packages needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1
# Auth is fail-closed by default (enforced unless AUTH_ENABLED=false).
CMD ["node", "dist/server/src/index.js"]
