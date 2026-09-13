# sales-app — WIM Online static frontend host (nginx)
FROM nginx:alpine

# nginx template uses API_HOST / API_PORT env to proxy /api/* to wim-api
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Static frontend files (html/js/css/assets)
COPY www/ /usr/share/nginx/html/

EXPOSE 80