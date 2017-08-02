#!/usr/bin/env python3
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

"""Main recognizer loop: wait for a trigger then perform and handle
recognition."""

import logging
import os
import os.path
import sys
import signal
import threading
import time

import configargparse

import aiy.audio
import auth_helpers
import action
import i18n
import speech
import tts

# =============================================================================
#
# Hey, Makers!
#
# Are you looking for actor.add_keyword? Do you want to add a new command?
# You need to edit src/action.py. Check out the instructions at:
# https://aiyprojects.withgoogle.com/voice/#makers-guide-3-3--create-a-new-voice-command-or-action
#
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(thread)d %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger('main')

# change these for your roombox and your client ID
# All of these could be extracted from roombox log except for CLIENT_AUTH_COOKIE
ENVIRONMENT_URL = 'go.nightly.fatline.io'
SHORT_DOMAIN = 'go'
ROOMBOX_DEVICE_ID = '58176a3560b218871466833a'
CLIENT_AUTH_COOKIE = 'device_id=2087ea94-7a01-4f2b-6fca-e11bf543eb8d; fatline-auth=CAAY7LyfutMrIiDLueUAAbpkn/LRZNIGlmLXN8yRtiHnlLVxCpZaI8qOZzAIOtMCCAASrgIKDFceg3pXcEghfcPY7BDn5K372SsYACIXYWhtZWQudmlsYUBoaWdoZml2ZS5jb20qBUFobWVkMgRWaWxhOkAKDFQsX7PksIYLriFQHBIMaGlnaGZpdmUuY29tGgJnbyABKgphaG1lZC52aWxhMAE4AEDBq8b5xCpI8Ja0rf8nSAFSEggBEgxULF+z5LCGC64hUBwYAFISCAASDFQsX7PksIYLriFQHBgAUhIIBBIMVCxfs+SwhguuIVAcGABaAggAYMGrxvnEKnJgCgJnbxIYNTQyYzVmYjNlNGIwODYwYmFlMjE1MDFjGgQICBABGgQICRABGgQIARABGgQIAhABGgQIAxABGgQIBRABGgQIBBABGgQIChABGgQIDBABGgQIDhABGgQIDRABegIIAiIeCgxXHoN6V3BIIX3D2OkSCmltYWdlL2pwZWcYZCBk; intercom-session-u0roaklw=TmIrR3B1YWMzUkZYSUYwdlcydUd5ODJJb0dvWmtOc3RsbFBJSEVLMTRuRjNDaHIyOHVhV1FQZkpTOGY1QzN6Yi0tZHJsUmpPWENIaVd3ZHpZU0g1N1Zodz09--612bf2275ed03fb92ccd398aaec04a620e3fa482'
# roombox identity doesn't have a permission to request imediate join, so prepareToConnectRoombox response might not have challenge_token
# challenge_token is dumped to log as sent from server, so additional log parsing has to happen if we're using roombox identity to call connectRoombox
# for that reason, grab user's fatline-auth from native-app's or chrome's network console

CONFIG_DIR = os.getenv('XDG_CONFIG_HOME') or '/var/persist/roombox'
CONFIG_FILES = [
    '/etc/voice-recognizer.ini',
    os.path.join(CONFIG_DIR, 'voice-recognizer.ini')
]

# Legacy fallback: old locations of secrets/credentials.
OLD_CLIENT_SECRETS = os.path.expanduser('/var/persist/roombox/client_secrets.json')
OLD_SERVICE_CREDENTIALS = os.path.expanduser('~/credentials.json')

ASSISTANT_CREDENTIALS = (
    '/var/persist/roombox/assistant_credentials.json'
)

HOTWORD_MODEL_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "snowboy", "resources", "Highfive.pmdl")


def try_to_get_credentials(client_secrets):
    """Try to get credentials, or print an error and quit on failure."""

    if os.path.exists(ASSISTANT_CREDENTIALS):
        return auth_helpers.load_credentials(ASSISTANT_CREDENTIALS)

    if not os.path.exists(client_secrets) and os.path.exists(OLD_CLIENT_SECRETS):
        client_secrets = OLD_CLIENT_SECRETS

    if not os.path.exists(client_secrets):
        print('You need client secrets to use the Assistant API.')
        print('Follow these instructions:')
        print('    https://developers.google.com/api-client-library/python/auth/installed-app'
              '#creatingcred')
        print('and put the file at', client_secrets)
        sys.exit(1)

    if not os.getenv('DISPLAY') and not sys.stdout.isatty():
        print("""
To use the Assistant API, manually start the application from the dev terminal.
See the "Turn on the Assistant API" section of the Voice Recognizer
User's Guide for more info.""")
        sys.exit(1)

    credentials = auth_helpers.credentials_flow_interactive(client_secrets)
    auth_helpers.save_credentials(ASSISTANT_CREDENTIALS, credentials)
    logging.info('OAuth credentials initialized: %s', ASSISTANT_CREDENTIALS)
    return credentials


def create_pid_file(file_name):
    if not file_name:
        # Try the default locations of the pid file, preferring /run/user as
        # it uses tmpfs.
        pid_dir = '/run/user/%d' % os.getuid()
        if not os.path.isdir(pid_dir):
            pid_dir = '/tmp'
        file_name = os.path.join(pid_dir, 'voice-recognizer.pid')

    with open(file_name, 'w') as pid_file:
        pid_file.write("%d" % os.getpid())


def main():
    parser = configargparse.ArgParser(
        default_config_files=CONFIG_FILES,
        description="Act on voice commands using Google's speech recognition")
    parser.add_argument('-I', '--input-device', default='default',
                        help='Name of the audio input device')
    parser.add_argument('-O', '--output-device', default='default',
                        help='Name of the audio output device')
    parser.add_argument('-T', '--trigger', default='gpio',
                        choices=['clap', 'gpio', 'ok-google', 'ok-snowboy'], help='Trigger to use')
    parser.add_argument('--cloud-speech', action='store_true',
                        help='Use the Cloud Speech API instead of the Assistant API')
    parser.add_argument('-L', '--language', default='en-US',
                        help='Language code to use for speech (default: en-US)')
    parser.add_argument('-l', '--led-fifo', default='/tmp/status-led',
                        help='Status led control fifo')
    parser.add_argument('-p', '--pid-file',
                        help='File containing our process id for monitoring')
    parser.add_argument('--audio-logging', action='store_true',
                        help='Log all requests and responses to WAV files in /tmp')
    parser.add_argument('--assistant-always-responds', action='store_true',
                        help='Play Assistant responses for local actions.'
                        ' You should make sure that you have IFTTT applets for'
                        ' your actions to get the correct response, and also'
                        ' that your actions do not call say().')
    parser.add_argument('--assistant-secrets',
                        default=os.path.expanduser('~/assistant.json'),
                        help='Path to client secrets for the Assistant API')
    parser.add_argument('--cloud-speech-secrets',
                        default=os.path.expanduser('~/cloud_speech.json'),
                        help='Path to service account credentials for the '
                        'Cloud Speech API')
    parser.add_argument('--trigger-sound', default=None,
                        help='Sound when trigger is activated (WAV format)')

    args = parser.parse_args()

    create_pid_file(args.pid_file)
    i18n.set_language_code(args.language, gettext_install=True)

    player = aiy.audio.Player(args.output_device)

    if args.cloud_speech:
        credentials_file = os.path.expanduser(args.cloud_speech_secrets)
        if not os.path.exists(credentials_file) and os.path.exists(OLD_SERVICE_CREDENTIALS):
            credentials_file = OLD_SERVICE_CREDENTIALS
        recognizer = speech.CloudSpeechRequest(credentials_file)
    else:
        credentials = try_to_get_credentials(
            os.path.expanduser(args.assistant_secrets))
        recognizer = speech.AssistantSpeechRequest(credentials)

    status_ui = StatusUi(player, args.led_fifo, args.trigger_sound)

    # The ok-google trigger is handled with the Assistant Library, so we need
    # to catch this case early.
    if args.trigger == 'ok-google':
        if args.cloud_speech:
            print('trigger=ok-google only works with the Assistant, not with '
                  'the Cloud Speech API.')
            sys.exit(1)
        do_assistant_library(args, recognizer, credentials, player, status_ui)
    elif args.trigger == 'ok-snowboy':
        if args.cloud_speech:
            print('trigger=ok-snowboy only works with the Assistant, not with '
                  'the Cloud Speech API.')
            sys.exit(1)
        do_snowboy(args, recognizer, credentials, player, status_ui)
    else:
        recorder = aiy.audio.Recorder(
            input_device=args.input_device, channels=1,
            bytes_per_sample=speech.AUDIO_SAMPLE_SIZE,
            sample_rate_hz=speech.AUDIO_SAMPLE_RATE_HZ)
        with recorder:
            do_recognition(args, recorder, recognizer, player, status_ui)

def do_snowboy(args, recognizer, credentials, player, status_ui):
    """Run a recognizer using snowboy hotword detector and continue 
    conversation using Google Assistant SDK (gRPC) in order to avoid google's hotword.
    """

    say = tts.create_say(player)
    actor = action.make_actor(say, ENVIRONMENT_URL, SHORT_DOMAIN, ROOMBOX_DEVICE_ID, CLIENT_AUTH_COOKIE)
    action.add_commands_just_for_cloud_speech_api(actor, say)

    recognizer.add_phrases(actor)
    
    status_ui.status('initializing snowboy')
    from snowboy import snowboydecoder
    detector = snowboydecoder.HotwordDetector(HOTWORD_MODEL_PATH, sensitivity=0.5)
    
    from assistant import Assistant
    assistant = Assistant(credentials)
    
    interrupted = False
    def signal_handler(signal, frame):
        interrupted = True
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    def interrupt_callback():
      return interrupted;

    def recognized_callback(spoken_text):
      if actor.can_handle(spoken_text):
        actor.handle(spoken_text)
        return args.assistant_always_responds
      return True

    def detect_callback():
      logger.info('snowboy detected hotword')
      detector.terminate()
      #snowboydecoder.play_audio_file(snowboydecoder.DETECT_DING)
      # Assistant is using sounddevice module, an interface to PortAudio
      # Since it's using RawStream, PortAudio is acquiring exclusive lock on a device
      # Since roombox-app is using it, exclusive lock can not be acquired
      # TODO: change assistant to use pyaudio
      try:
        assistant.assist(recognized_callback)
      except:
        logger.warning('assistant could not acquire audio input stream')
      logger.info('snowboy restart')
      #snowboydecoder.play_audio_file(snowboydecoder.DETECT_DONG)
      detector.do_init("snowboy/resources/Highfive.pmdl", sensitivity=0.5)
      detector.start(detected_callback=detect_callback,
                 interrupt_check=interrupt_callback,
                 sleep_time=0.03)

    status_ui.status('snowboy all set')
    detector.start(detected_callback=detect_callback,
               interrupt_check=interrupt_callback,
               sleep_time=0.03)

    detector.terminate()

def do_assistant_library(args, recognizer, credentials, player, status_ui):
    """Run a recognizer using the Google Assistant Library.

    The Google Assistant Library has direct access to the audio API, so this
    Python code doesn't need to record audio.
    """

    try:
        from google.assistant.library import Assistant
        from google.assistant.library.event import EventType
    except ImportError:
        print('''
ERROR: failed to import the Google Assistant Library. This is required for
"OK Google" hotwording, but is only available for Raspberry Pi 2/3. It can be
installed with:
    env/bin/pip install google-assistant-library==0.0.2''')
        sys.exit(1)

    say = tts.create_say(player)
    actor = action.make_actor(say)
    action.add_commands_just_for_cloud_speech_api(actor, say)

    recognizer.add_phrases(actor)
    
    status_ui.status('initializing snowboy')
    from snowboy import snowboydecoder
    detector = snowboydecoder.HotwordDetector("snowboy/resources/Highfive.pmdl", sensitivity=0.5)
    
    interrupted = False
    def signal_handler(signal, frame):
        interrupted = True
        logger.info('interrupted')
        #sys.exit(1)

    #signal.signal(signal.SIGINT, signal_handler)

    def interrupt_callback():
      return False;

    def do_assist():
      with Assistant(credentials) as assistant:
        def process_event(event):
            logging.info(event)

            if event.type == EventType.ON_START_FINISHED:
                status_ui.status('ready')
                if sys.stdout.isatty():
                    print('Say "OK, Google" then speak, or press Ctrl+C to quit...')

                assistant.start_conversation()
                logger.info('Trying to listen')

            elif event.type == EventType.ON_CONVERSATION_TURN_STARTED:
                status_ui.status('listening')

            elif event.type == EventType.ON_END_OF_UTTERANCE:
                status_ui.status('thinking')

            elif event.type == EventType.ON_RECOGNIZING_SPEECH_FINISHED and \
                    event.args and actor.can_handle(event.args['text']):
                if not args.assistant_always_responds:
                    assistant.stop_conversation()
                actor.handle(event.args['text'])

            elif event.type == EventType.ON_CONVERSATION_TURN_FINISHED:
                status_ui.status('ready')
                return False

            elif event.type == EventType.ON_ASSISTANT_ERROR and \
                    event.args and event.args['is_fatal']:
                status_ui.status('terminating')
                return False
                #sys.exit(1)

            return True

        for event in assistant.start():
            rtn = process_event(event)
            logger.info('return %s...', rtn)
            if not rtn:
              logger.info('breaking out')
              assistant.set_mic_mute(True)
              logger.info('broke out')
              break
        logger.info('alive 1')
      logger.info('alive 2')
      
    def detect_callback():
      logger.info('snowboy detected hotword')
      detector.terminate()
      #snowboydecoder.play_audio_file(snowboydecoder.DETECT_DING)
      do_assist()
      logger.info('snowboy restart')
      #snowboydecoder.play_audio_file(snowboydecoder.DETECT_DONG)
      detector.do_init("snowboy/resources/Highfive.pmdl", sensitivity=0.5)
      detector.start(detected_callback=detect_callback,
                 interrupt_check=interrupt_callback,
                 sleep_time=0.03)

    status_ui.status('snowboy all set')
    detector.start(detected_callback=detect_callback,
               interrupt_check=interrupt_callback,
               sleep_time=0.03)

    logger.info('finishing')
    detector.terminate()
    

def do_recognition(args, recorder, recognizer, player, status_ui):
    """Configure and run the recognizer."""
    say = tts.create_say(player)

    actor = action.make_actor(say)

    #if args.cloud_speech:
    action.add_commands_just_for_cloud_speech_api(actor, say)

    recognizer.add_phrases(actor)
    recognizer.set_audio_logging_enabled(args.audio_logging)

    if args.trigger == 'gpio':
        import triggers.gpio
        triggerer = triggers.gpio.GpioTrigger(channel=23)
        msg = 'Press the button on GPIO 23'
    elif args.trigger == 'clap':
        import triggers.clap
        triggerer = triggers.clap.ClapTrigger(recorder)
        msg = 'Clap your hands'
    else:
        logger.error("Unknown trigger '%s'", args.trigger)
        return

    mic_recognizer = SyncMicRecognizer(
        actor, recognizer, recorder, player, say, triggerer, status_ui,
        args.assistant_always_responds)

    with mic_recognizer:
        if sys.stdout.isatty():
            print(msg + ' then speak, or press Ctrl+C to quit...')

        # wait for KeyboardInterrupt
        while True:
            time.sleep(1)


class StatusUi(object):

    """Gives the user status feedback.

    The LED and optionally a trigger sound tell the user when the box is
    ready, listening or thinking.
    """

    def __init__(self, player, led_fifo, trigger_sound):
        self.player = player

        if led_fifo and os.path.exists(led_fifo):
            self.led_fifo = led_fifo
        else:
            if led_fifo:
                logger.warning(
                    'File %s specified for --led-fifo does not exist.',
                    led_fifo)
            self.led_fifo = None

        if trigger_sound and os.path.exists(os.path.expanduser(trigger_sound)):
            self.trigger_sound = os.path.expanduser(trigger_sound)
        else:
            if trigger_sound:
                logger.warning(
                    'File %s specified for --trigger-sound does not exist.',
                    trigger_sound)
            self.trigger_sound = None

    def status(self, status):
        if self.led_fifo:
            with open(self.led_fifo, 'w') as led:
                led.write(status + '\n')
        logger.info('%s...', status)

        if status == 'listening' and self.trigger_sound:
            self.player.play_wav(self.trigger_sound)


class SyncMicRecognizer(object):

    """Detects triggers and runs recognition in a background thread.

    This is a context manager, so it will clean up the background thread if the
    main program is interrupted.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, actor, recognizer, recorder, player, say, triggerer,
                 status_ui, assistant_always_responds):
        self.actor = actor
        self.player = player
        self.recognizer = recognizer
        self.recognizer.set_endpointer_cb(self.endpointer_cb)
        self.recorder = recorder
        self.say = say
        self.triggerer = triggerer
        self.triggerer.set_callback(self.recognize)
        self.status_ui = status_ui
        self.assistant_always_responds = assistant_always_responds

        self.running = False

        self.recognizer_event = threading.Event()

    def __enter__(self):
        self.running = True
        threading.Thread(target=self._recognize).start()
        self.triggerer.start()
        self.status_ui.status('ready')

    def __exit__(self, *args):
        self.running = False
        self.recognizer_event.set()

        self.recognizer.end_audio()

    def recognize(self):
        if self.recognizer_event.is_set():
            # Duplicate trigger (eg multiple button presses)
            return

        self.status_ui.status('listening')
        self.recognizer.reset()
        self.recorder.add_processor(self.recognizer)
        # Tell recognizer to run
        self.recognizer_event.set()

    def endpointer_cb(self):
        self.recorder.del_processor(self.recognizer)
        self.status_ui.status('thinking')

    def _recognize(self):
        while self.running:
            self.recognizer_event.wait()
            if not self.running:
                break

            logger.info('recognizing...')
            try:
                self._handle_result(self.recognizer.do_request())
            except speech.Error:
                logger.exception('Unexpected error')
                self.say(_('Unexpected error. Try again or check the logs.'))

            self.recognizer_event.clear()
            if self.recognizer.dialog_follow_on:
                self.recognize()
            else:
                self.triggerer.start()
                self.status_ui.status('ready')

    def _handle_result(self, result):
        if result.transcript and self.actor.handle(result.transcript):
            logger.info('handled local command: %s', result.transcript)
            if result.response_audio and self.assistant_always_responds:
                self._play_assistant_response(result.response_audio)
        elif result.response_audio:
            self._play_assistant_response(result.response_audio)
        elif result.transcript:
            logger.warning('%r was not handled', result.transcript)
        else:
            logger.warning('no command recognized')

    def _play_assistant_response(self, audio_bytes):
        bytes_per_sample = speech.AUDIO_SAMPLE_SIZE
        sample_rate_hz = speech.AUDIO_SAMPLE_RATE_HZ
        logger.info('Playing %.4f seconds of audio...',
                    len(audio_bytes) / (bytes_per_sample * sample_rate_hz))
        self.player.play_bytes(audio_bytes, sample_width=bytes_per_sample,
                               sample_rate=sample_rate_hz)


if __name__ == '__main__':
    main()
