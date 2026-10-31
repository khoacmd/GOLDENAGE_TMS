# Web (React build tĩnh) + nginx: phục vụ SPA, proxy /api → api, /tiles (bản đồ), ảnh S3 → storage.
# Build từ thư mục gốc repo: docker buildx build -f web/Dockerfile .
FROM --platform=$BUILDPLATFORM node:24-alpine AS build
RUN corepack enable
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web/package.json web/
COPY mobile/package.json mobile/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter web...
COPY packages/api-client packages/api-client
COPY web web
RUN pnpm --filter web build

FROM nginx:1.27-alpine
COPY infra/prod/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/web/dist /usr/share/nginx/html
