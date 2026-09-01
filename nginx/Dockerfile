FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY ssl.conf.template /etc/nginx/ssl.conf.template
COPY docker-entrypoint.d/40-ssl.sh /docker-entrypoint.d/40-ssl.sh
RUN chmod +x /docker-entrypoint.d/40-ssl.sh
