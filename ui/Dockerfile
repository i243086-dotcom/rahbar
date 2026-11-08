FROM nginxinc/nginx-unprivileged:1.28-alpine AS assets
COPY index.html /site/index.html
FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=assets /site/index.html /usr/share/nginx/html/index.html
USER 101:101
ENTRYPOINT ["nginx", "-g", "daemon off;"]
