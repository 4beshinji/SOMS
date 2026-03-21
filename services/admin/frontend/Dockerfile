# Build Stage — context is project root (monorepo)
FROM node:22-alpine AS build
WORKDIR /workspace

# Copy workspace config + lockfile + root package.json
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Copy workspace packages
COPY packages/ packages/

# Copy admin-frontend package.json for dependency resolution
COPY services/admin/frontend/package.json services/admin/frontend/

# Install pnpm and all dependencies
RUN npm install -g pnpm@10.30.0 \
    && pnpm install --frozen-lockfile

# Copy admin-frontend source and build
COPY services/admin/frontend/ services/admin/frontend/
RUN pnpm --filter soms-admin run build

# Production Stage
FROM nginx:alpine
COPY --from=build /workspace/services/admin/frontend/dist /usr/share/nginx/html
COPY services/admin/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
