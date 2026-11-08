FROM ghcr.io/nginx/nginx-unprivileged:1.30.6-alpine3.24-slim AS assets
COPY index.html /site/index.html
FROM ghcr.io/nginx/nginx-unprivileged:1.30.6-alpine3.24-slim
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=assets /site/index.html /usr/share/nginx/html/index.html
USER 101:101
ENTRYPOINT ["nginx", "-g", "daemon off;"]
