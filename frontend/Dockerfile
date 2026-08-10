# Frontend + edge image: build the Vite app, then serve it with Caddy and
# reverse-proxy /v1/* to the API. Caddy is the single public entrypoint.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build against the real backend (disable the in-browser mock).
ENV VITE_USE_MOCKS=false
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
