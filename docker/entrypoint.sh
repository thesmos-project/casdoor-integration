#!/bin/sh
set -eu
if [ ! -r /conf/app.conf ]; then
  echo 'Mount a readable Casdoor configuration at /conf/app.conf before starting.' >&2
  exit 1
fi
exec /server "$@"
