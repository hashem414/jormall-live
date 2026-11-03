FROM node:24-bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g pnpm@10.33.2
WORKDIR /app
COPY source.tar.gz /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz -C /app
RUN pnpm install --frozen-lockfile
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_URL=postgresql://build:REDACTED_CONFIGURE_LOCALLY@127.0.0.1:5432/build
ENV NEXT_PUBLIC_APP_URL=https://appointments.jormallapp.com
ENV AUTH_SECRET=build-only-placeholder-not-a-runtime-secret
RUN pnpm db:generate
RUN pnpm build
RUN cp -r apps/web/.next/static apps/web/.next/standalone/apps/web/.next/static

FROM node:24-bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g pnpm@10.33.2
WORKDIR /app
COPY --from=build --chown=node:node /app /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
USER node
WORKDIR /app/apps/web
EXPOSE 3000
CMD ["node", ".next/standalone/apps/web/server.js"]
