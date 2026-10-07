FROM golang:1.26-alpine AS builder

WORKDIR /app

COPY . .

RUN GO111MODULE=auto CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o bot pusher.go

FROM alpine:3.22

WORKDIR /root/

COPY --from=builder /app/bot .

RUN apk --no-cache add ca-certificates

CMD ["./bot"]