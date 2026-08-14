# Frontend: build the React app, then serve it with Caddy (which also terminates
# TLS via Let's Encrypt and reverse-proxies /api to the backend).
# Build context is the REPO ROOT.
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
