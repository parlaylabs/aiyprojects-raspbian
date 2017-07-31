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

mount -o rw,remount /

# Fool OTA to avoid update
echo "v10.28.0-51-g0c83551" > /etc/hyperion-version

scripts_dir="$(dirname "${BASH_SOURCE[0]}")"

# make sure we're running as the owner of the checkout directory
RUN_AS="$(ls -ld "$scripts_dir" | awk 'NR==1 {print $3}')"
if [ "$USER" != "$RUN_AS" ]
then
    echo "This script must run as $RUN_AS, trying to change user..."
    exec sudo -u $RUN_AS $0
fi

cd ${scripts_dir}/../

wget https://d1uy6kk12x9igo.cloudfront.net/roombox-test/google-assistant-deps.zip --no-check-certificate
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

pushd google-assistant-deps/snowboy_deps
dpkg -i --force-depends *.deb
popd

# Newer version of certifi has removed trusted root certificates from their packages 
# and relies on system wide ones that are not installed, so we're downgrading this package
#python3 -m pip uninstall certifi
#python3 -m pip install certifi-2015.04.28

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

wget https://d1uy6kk12x9igo.cloudfront.net/roombox/v2.29.0-13-g39c9be1/fatline-roombox.deb --no-check-certificate
dpkg -i fatline-roombox.deb

# this should go into the startup script
mkdir -p /tmp/leds-app/led0-blue/device/
mkdir -p /tmp/leds-app/led0-red/device/

ln -snf /tmp/leds-app /tmp/leds
ln -snf /sys/class/leds /tmp/leds

# temporary hack to get libgfortran and other libs for arm-linux-gnueabihf specifically into libraries path
mv /usr/lib/arm-linux-gnueabihf/libgfortran.so.3* /usr/lib/
mv /lib/arm-linux-gnueabihf/* /lib/

#
#multiarch-support_2.19-0ubuntu6.13_armhf.deb
#libgfortran3_4.8.4-2ubuntu1-14.04.3_armhf.deb
#mv /usr/lib/arm-linux-gnueabihf/libgfortran.so.3* /usr/lib/
#libatlas3-base_3.10.1-4_armhf.deb
#libatlas-base-dev_3.10.1-4_armhf.deb

#install swig to build python3 snowboy:
#libpcre3_8.39-3_armhf.deb
#zlib1g_1.2.11.dfsg-0ubuntu1_armhf.deb
#swig_3.0.10-1.1_armhf.deb
#swig3.0_3.0.10-1.1_armhf.deb
#mv /lib/arm-linux-gnueabihf/* /lib/