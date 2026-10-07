#!/bin/bash


cd "$(dirname "$(readlink -f "$(which "$0")")")" || exit

mkdir -p "../$1" &&
ln -i ./* "../$1"