#!/bin/bash

set -o errexit

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 1>&2
   exit 1
fi

scripts_dir="$(dirname "${BASH_SOURCE[0]}")"

cp $scripts_dir/run.sh /etc/init.d/google_assistant.sh
chmod a+x /etc/init.d/google_assistant.sh