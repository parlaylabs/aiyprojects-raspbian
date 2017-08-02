# Highfive-specific deployment

- Download this repo as a zip file and push it to /home/highfive on roombox
- unzip file and rename it to aiyprojects-raspbian
- run scripts/install-deps.sh
- run scripts/install-alsa-config.sh
- run scripts/run.sh
- it will prompt to go to google oauth2 URL and allow this application to use google assistant
- copy and paste oauth2 key and continue
- if everything is set you should see a message `snowboy all set...`. Then exit via CMD/CTRL-C

You can now ask `OK Highfive, what is the weather today` and you should hear response on your TV and at the same time you should see transcript of your request in ADB console where you have run assistant

Further on, to be able to do meeting controls:
- Using native-app or Chrome join a call on the same domain where roombox is provisioned
- Open console and take any network request's details that points to the highfive's server for that environment
- Copy fatline-auth and device_id from Cookie header
- open src/main.py and update CLIENT_AUTH_COOKIE with fatline-auth and device_id
- run scripts/install-service.sh
- restart roombox
- try `OK Highfive, what is the weather today` again and confirm there is a response
- try `OK Highfive, join meeting test` and it should join that meeting

### Notes

Yocto recipes to build python3 and it's dependencies along with pip:
https://github.com/parlaylabs/yocto/tree/avila/roombox-temp

Snowboy repo that is used to build _snowboydetect.so for roombox:
https://github.com/Kitt-AI/snowboy

google assistant supports only 16kHz audio while we have forced 48kHz on a kernel level.
Thus, .asoundrc is modified to add resampler. Resampler will not affect roombox-app since it requests 48kHz audio, but will allow google assistant to request resampled 16kHz audio from microphone.

# Original README

This repository contains the source code for the AIYProjects "Voice Kit". See
https://aiyprojects.withgoogle.com/voice/.

If you're using Rasbian instead of Google's provided image, read
[HACKING.md](HACKING.md) for information on getting started.

[![Build Status](https://travis-ci.org/google/aiyprojects-raspbian.svg?branch=master)](https://travis-ci.org/google/aiyprojects-raspbian/builds)
[![Test Coverage](https://codecov.io/gh/google/aiyprojects-raspbian/branch/master/graph/badge.svg)](https://codecov.io/gh/google/aiyprojects-raspbian)

## Troubleshooting

The scripts in the `checkpoints` directory verify the Raspberry Pi's setup.
They can be run from the desktop shortcuts or from the terminal.
