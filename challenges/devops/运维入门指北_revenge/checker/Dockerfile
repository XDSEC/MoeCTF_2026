FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go env -w GOPROXY=https://goproxy.cn,direct && go mod download
COPY checker.go .
RUN CGO_ENABLED=0 GOOS=linux go build -o checker checker.go

FROM nginx:alpine

RUN echo 'server { \
    listen 80; \
    server_name _; \
    location / { \
        proxy_pass http://127.0.0.1:8080; \
        proxy_set_header Host blog.moectf; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header Accept-Encoding ""; \
        sub_filter "http://blog.moectf" "$scheme://$http_host"; \
        sub_filter_once off; \
        sub_filter_types text/html text/css text/xml application/javascript; \
        proxy_redirect http://blog.moectf/ http://$http_host/; \
    } \
}' > /etc/nginx/conf.d/default.conf

COPY --from=builder /app/checker /usr/local/bin/checker

CMD ["/bin/sh", "-c", "nginx && /usr/local/bin/checker"]