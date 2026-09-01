FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY ssl.conf.template /etc/nginx/ssl.conf.template
COPY entrypoint.sh /nginx-entrypoint.sh
RUN chmod +x /nginx-entrypoint.sh
ENTRYPOINT ["/nginx-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
