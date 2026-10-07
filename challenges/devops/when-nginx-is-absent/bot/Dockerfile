FROM alpine:3.18

RUN apk add --no-cache python3 py3-pip && \
    pip3 install --no-cache-dir requests

WORKDIR /app
COPY bot.py .

CMD ["python3", "bot.py"]