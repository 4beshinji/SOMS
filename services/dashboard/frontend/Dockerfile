# Build Stage — context is project root (monorepo)
FROM node:22-alpine AS builder
WORKDIR /workspace

# Copy workspace config + lockfile + root package.json
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Copy workspace packages
COPY packages/ packages/

# Copy frontend package.json for dependency resolution
COPY services/dashboard/frontend/package.json services/dashboard/frontend/

# Install pnpm and all dependencies
RUN npm install -g pnpm@10.30.0 \
    && pnpm install --frozen-lockfile

# Copy frontend source and build
COPY services/dashboard/frontend/ services/dashboard/frontend/
RUN pnpm --filter frontend run build

# Production Stage
FROM nginx:alpine
COPY --from=builder /workspace/services/dashboard/frontend/dist /usr/share/nginx/html
COPY services/dashboard/frontend/nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /usr/share/nginx/html \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid
USER nginx

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
