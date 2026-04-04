# Build Stage — context is project root (monorepo)
FROM node:22-alpine AS builder
WORKDIR /workspace

# Copy workspace config + lockfile + root package.json
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Copy workspace packages
COPY packages/ packages/

# Copy wallet-app package.json for dependency resolution
COPY services/wallet-app/package.json services/wallet-app/

# Install pnpm and all dependencies
RUN npm install -g pnpm@10.30.0 \
    && pnpm install --frozen-lockfile

# Copy wallet-app source and build
COPY services/wallet-app/ services/wallet-app/
RUN pnpm --filter soms-wallet-app run build

# Production Stage
FROM nginx:alpine
RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout /etc/nginx/ssl/key.pem \
      -out /etc/nginx/ssl/cert.pem \
      -subj "/CN=soms-wallet-app"
COPY --from=builder /workspace/services/wallet-app/dist /usr/share/nginx/html
COPY services/wallet-app/nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /usr/share/nginx/html \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid \
    && chmod 644 /etc/nginx/ssl/cert.pem /etc/nginx/ssl/key.pem
USER nginx

EXPOSE 8080 8443
CMD ["nginx", "-g", "daemon off;"]
