# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# No secrets at build time: all configuration is read from the environment at runtime.
RUN AUTH_SECRET=build-time-placeholder npm run build

FROM base AS runtime
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S -g 10001 glideup && adduser -S -u 10001 -G glideup glideup
COPY --from=build --chown=glideup:glideup /app/.next/standalone ./
COPY --from=build --chown=glideup:glideup /app/.next/static ./.next/static
COPY --from=build --chown=glideup:glideup /app/public ./public
USER glideup
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["node", "server.js"]
