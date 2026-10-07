#!/bin/sh

echo "$FLAG" > "/tmp/flag"
# export FLAG="flag{is-this-a-real-flag}"

FILE=$(which "$0")
DIR=$(dirname "$FILE")

exec /usr/local/bin/python "$DIR/main.py" "$@"