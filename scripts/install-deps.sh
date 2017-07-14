#!/bin/bash
# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -o errexit

scripts_dir="$(dirname "${BASH_SOURCE[0]}")"

# make sure we're running as the owner of the checkout directory
RUN_AS="$(ls -ld "$scripts_dir" | awk 'NR==1 {print $3}')"
if [ "$USER" != "$RUN_AS" ]
then
    echo "This script must run as $RUN_AS, trying to change user..."
    exec sudo -u $RUN_AS $0
fi

pushd ../
wget https://d1uy6kk12x9igo.cloudfront.net/roombox-test/google-assistant-deps.zip
unzip google-assistant-deps.zip

pushd google-assistant-deps/gcc
dpkg -i --force-depends *.deb
popd

pushd google-assistant-deps/python3
dpkg -i --force-depends *.deb
popd

pushd google-assistant-deps/libffi
dpkg -i --force-depends *.deb
popd
popd

# Newer version of certifi has removed trusted root certificates from their packages 
# and relies on system wide ones that are not installed, so we're downgrading this package
python3 -m pip uninstall certifi

python3 -m pip install -r requirements.txt

#sudo -u highfive google-oauthlib-tool --client-secrets /var/persist/roombox/assistant.json --scope https://www.googleapis.com/auth/assistant-sdk-prototype --save --headless

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

#sudo apt-get -y install alsa-utils python3-all-dev python3-pip python3-numpy \
#  python3-scipy python3-virtualenv python3-rpi.gpio python3-pysocks \
#  rsync sox libttspico-utils ntpdate
#sudo pip3 install --upgrade pip virtualenv

#cd "${scripts_dir}/.."
#virtualenv --system-site-packages -p python3 env
#env/bin/pip install -r requirements.txt

# The google-assistant-library is only available on ARMv7.
if [[ "$(uname -m)" == "armv7l" ]] ; then
  python3 -m pip install google-assistant-library==0.0.2
fi

config=voice-recognizer.ini
if [[ ! -f "${HOME}/.config/${config}" ]] ; then
  echo "Installing ${config}"
  cp "config/${config}.default" "${HOME}/.config/${config}"
fi
