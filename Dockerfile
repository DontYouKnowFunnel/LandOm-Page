FROM nginx:1.27-alpine

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 docker-entrypoint.d/40-generate-landom-sdk-init.sh /docker-entrypoint.d/40-generate-landom-sdk-init.sh
COPY --chmod=755 docker-entrypoint.d/50-generate-meta-pixel.sh /docker-entrypoint.d/50-generate-meta-pixel.sh
COPY pages /usr/share/nginx/html/pages
COPY assets /usr/share/nginx/html/assets

EXPOSE 80
