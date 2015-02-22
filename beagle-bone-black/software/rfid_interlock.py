#! /usr/bin/python

"""
This module implement a very generic rfid reader / controller as a very
intracate finite state machine where.  The main actors are:
    the message queue in which each message is a dictionary of the following:
        "state": the next state as documented in MessageTypes
        "from": a string describing the connection generating the new state
        "badge_id": optional, the rfid of the badge to be checked

    Interlock class:
        akin to an operating system's kernal

    Connection classes:
        Basically, each of these implement a connection whether is be an
        rfid reader, an digitial input, digital output, analog input,
        webservice to verify a rfid number, a mysql connection to verify
        a rfid number or to log activity, lcd to show the current state.

"""
#
#  contact Brooks Scarff for Networks
#  contact Paul Brown for config
#
#  Gus Reiter todo:
#    play with current sensing
#    play with PIR
#    handle errors
#    document
#

from datetime import datetime, timedelta
import time, json, serial, threading, Queue, sys, fcntl, os

from evdev import InputDevice, ecodes
import lcd_i2c_p018

import urllib2
from uuid import getnode as get_mac_address

import Adafruit_BBIO.ADC  as ADC
import Adafruit_BBIO.GPIO as GPIO

import configuration

import logging
import logging.config
import logging.handlers

################################################################################
#
#  action_queue
#
################################################################################

class MessageTypes(object):
    """
    this class contains all of the different states that a connection can be in
    and messages that can be passed through the messaging queue

    ALL_STATES is a list of the mesasges that a connection can receive
    """
    POWER_UP = "power_up"

    ACTIVE = "active"
    INACTIVE_SOON = "inactive_soon"
    INACTIVE = "inactive"

    ERROR = "error"
    ERROR_CONFIG = "error:config"
    ERROR_NETWORK = "error:network"
    ERROR_MAINTENANCE = "error:maintenance"

    TESTING_NETWORK = "testing_network"

    CHECK_BADGE = "check_badge"
    LOGIN_DENIED = "login_denied"

    RESET_TIMER = "reset_timer"

    ALL_STATES = [
        POWER_UP,
        ACTIVE,
        INACTIVE_SOON,
        INACTIVE,
        ERROR,
        ERROR_CONFIG,
        ERROR_NETWORK,
        ERROR_MAINTENANCE,
        TESTING_NETWORK,
        CHECK_BADGE,
        LOGIN_DENIED
    ]

    INFO_ONLY = [
        TESTING_NETWORK,
        CHECK_BADGE,
        LOGIN_DENIED
    ]

    INTERLOCK_CLASS = ALL_STATES + [RESET_TIMER]

################################################################################
#
#  custom logging handler
#
################################################################################

class ErrorArrayHandler(logging.Handler):
    """
    this is a logging handler which puts all messages that it receives into an
    array so that you can display them later if you like.

    http://pantburk.info/?blog=77
    """
    def __init__(self):
        """
        takes no parameters
        """
        logging.Handler.__init__(self)
        self.clear_errors()
        self.errors = []

    def emit(self, record):
        """
        take note of an an error
        """
        self.errors.append(record)

    def clear_errors(self):
        """
        Clear out the errors that we have take note of so far.
        """
        self.errors = []

    def get_errors(self):
        """
        returns an array of the errors.
        """
        return self.errors

################################################################################
#
#  generic Connection controls
#
################################################################################

class Connection(object):
    """
    this is the generic connection class that must be subclassed.
    providing base functionality regardless of the output

    It saves the interlock parameter into itself.  This is actually the main
    Interlock object that runs everything, akin to the scheduler in Unix.
    The main attributes of interest are:
        action_queue: used to change the current state which is passed to all
            of the other connections.  Here is how to call it from a connection:

            self.interlock.action_queue.put({
                "state": MessageTypes.INACTIVE,
                "from": "BadgeReader.run() swipe out"})

        tool_id: This is especially usesful when validating a badge swipe for
            a specific tool.
    """

    def __init__(self, interlock, connection, config):
        """
        keep a pointer to the interlock object.
        """
        self.interlock = interlock
        self.connection = connection
        self.config = config
        self.run_continuously = False

    def update(self, status):
        """
        override this method which is called when a new state is attained.
        """
        pass


################################################################################
#
#  generic BadgeReader
#
################################################################################

class BadgeReader(threading.Thread, Connection):
    """
    This is the generic BadgeReader class that must be subclassed.  It starts a
    task to keep calling the readline() function on the input attribute, then
    massages the message read in, an puts the rfid id to test into the global
    queue.

    The readline() method which must be provided in the in any children classes.
    """
    def __init__(self, interlock, connection, config):
        """
        the config is a dictionary that can contains several atributes.

        code_skip_chars: how many characters to skip from the raw data.
        code_len: how many characters from the raw data to keep for the rfid.
        code_base: 10 if the rfid is in base 10, or 16 if it is hexadecimal.

        Children classes must instanciate the "input" attribute which must
        provide a readline() method.
        """
        # log = logging.getLogger("BadgeReader.init")

        threading.Thread.__init__(self)
        Connection.__init__(self, interlock, connection, config)
        self.run_continuously = True
        #
        # Help adapt to understand the rfid code
        #
        self.code_skip_chars = config.get("code_skip_chars", None)
        self.code_len = config.get("code_len", None)
        self.code_base = config.get("code_base", 16)

        #
        # for caching the rfid codes so that we are not unnecessarily hitting
        # makermanager
        #
        self.last_status = MessageTypes.INACTIVE
        self.ignore_for_now = dict()

        #
        # The child class must create an attribute which is an object with a
        # readline() method
        #
        self.input = None


    def run(self):
        """
        tells the Interlock when we scan a badge indicating a person wants
        permission to use this equipment
        """

        log_run = logging.getLogger("BadgeReader.run")
        log_read = logging.getLogger("BadgeReader.read")
        log_throttle = logging.getLogger("BadgeReader.throttle")
        log_code = logging.getLogger("BadgeReader.code")

        log_run.info("in BadgeReader.run()")

        ignore_scan_period = timedelta(seconds=1)

        while True:
            badge_raw = self.input.readline().rstrip()
            log_read.info("read in badge '" + badge_raw + "'")

            #
            # delete old scans
            #
            for del_badge in self.ignore_for_now.keys():
                log_throttle.info("comparing: " +
                        repr(self.ignore_for_now[del_badge]) +
                        " with " + repr(datetime.now()))
                if self.ignore_for_now[del_badge] < datetime.now():
                    log_throttle.info("removing " + repr(del_badge))
                    del self.ignore_for_now[del_badge]

            #
            # if the badge has been recently scanned, do not process it, but
            # remember that it was just now scanned.
            #
            log_throttle.debug("checking for " + badge_raw + " in " +
                    repr(self.ignore_for_now))
            if badge_raw in self.ignore_for_now:
                if badge_raw != "":
                    log_throttle.debug("ignoring " + badge_raw + " for now")
                    badge_raw = ""
            else:
                ignore_until = datetime.now() + ignore_scan_period
                self.ignore_for_now[badge_raw] = ignore_until
                log_throttle.debug("added " + badge_raw + " to " +
                        repr(self.ignore_for_now))

            if badge_raw != "":
                #
                # received a swipe while active, let's deactivate
                #
                if self.last_status == MessageTypes.ACTIVE:
                    self.interlock.action_queue.put({
                        "state": MessageTypes.INACTIVE,
                        "from": "BadgeReader.run() swipe out"})
                else:
                    #
                    # received a swipe while inactive, let's see if we have
                    # permission
                    #
                    try:
                        #
                        # extract the rfid
                        #
                        badge_raw = badge_raw[self.code_skip_chars:
                                self.code_len]
                        badge_decimal = str(int(badge_raw, self.code_base))
                        log_code.info("BadgeReader.run(): badge code is " +
                                    repr(badge_decimal))

                        self.interlock.action_queue.put(
                            {"state": MessageTypes.CHECK_BADGE,
                            "badge_id": badge_decimal,
                            "from": "BadgeReader.run()"})

                    except ValueError:
                        log_read.error(
                            "Cannot convert " + badge_raw + " into decimal")

    def update(self, action_message):
        """
        When the new state changes between Active, or Inactive, the then the
        read RFIDs cache is cleared.
        """
        status = action_message["state"]
        log_update = logging.getLogger("BadgeReader.update")
        if self.last_status != status:
            log_update.info("BadgeReader.update():" +
                        " status changed, clearing rfid cache")
            self.ignore_for_now.clear()

            #
            # we only care if about active or inactive states
            #
            if status in [MessageTypes.ACTIVE, MessageTypes.INACTIVE]:
                self.last_status = status

class SerialBadgeReader(BadgeReader):
    """
    serial BadgeReader
    """
    def __init__(self, interlock, connection, config):
        """
        config must be a diciontary which also contains the following:

        baud: the baud rate of the serial connection
        """
        log = logging.getLogger("SerialBadgeReader.init")
        log.info("in SerialBadgeReader.__init__()")
        BadgeReader.__init__(self, interlock, connection, config)
        if 'baud' in config:
            self.input = serial.Serial(connection, config['baud'])
        else:
            raise

################################################################################
#
#  stdin BadgeReader
#
################################################################################

class KeyboardBadgeReader(BadgeReader):
    """
    BadgeReader which reads the rfid codes from standard input.
    """
    def __init__(self, interlock, connection, config):
        """
        How many stdin's can we have?  No additional characteristics.
        """
        log = logging.getLogger("KeyboardBadgeReader.init")
        log.info("in KeyboardBadgeReader.__init__()")
        #
        # may need to pass connection into the parent __init__
        BadgeReader.__init__(self, interlock, connection, config)
        if connection == "stdin":
            self.input = sys.stdin
        else:
            raise

################################################################################
#
#  input_event BadgeReader
#
################################################################################

class InputEventStream(object):
    """
    This class provides a stream like interface into a device file that only
    responds to input event calls
    """
    def __init__(self, device_filename, scan_to_char_mapping=None):
        """
        device_filename is the file in /dev to open to read scan codes.
        scan_to_char_mapping is a list where the position in the array relates
        to the scan code, and the element in the array relates to the char.
        """
        log = logging.getLogger("InputEventBadgeReader.init")
        try:
            self.device = InputDevice(device_filename)
        except OSError:
            log.error("cannot open " + device_filename)
            raise

        if scan_to_char_mapping != None:
            self.scan_to_char_mapping = scan_to_char_mapping
        else:
            self.scan_to_char_mapping = ["", ""] + \
                [str(x) for x in range(1, 10)] + ['0'] + ([""] * 16) + ["\n"] +\
                [""] * 100

    def readline(self):
        """
        This provides the same functionality as readline from a serial device.
        """
        line = ""
        for event in self.device.read_loop():
            if event.type == ecodes.EV_KEY and event.value == 1:
                if self.scan_to_char_mapping[event.code] == "\n":
                    break
                else:
                    line += self.scan_to_char_mapping[event.code]
        return line

class InputEventBadgeReader(BadgeReader):
    """
    BadgeReader which reads the rfid codes from Human Interface Device such as
    a keyboard, or rfid reader plugged into usb port.
    """
    def __init__(self, interlock, connection, config):
        """
        connection must be the full filename of the device file which provides
        input event interface.
        """
        log = logging.getLogger("InputEventBadgeReader.init")
        log.info("in InputEventBadgeReader.__init__()")
        BadgeReader.__init__(self, interlock, connection, config)
        self.input = InputEventStream(connection)


################################################################################
#
#  hardcode specific badges to do specfic things
#
################################################################################

# badge_translation = {
#     "21505625070": {
#         "description": "blue keyfob",
#         "translate_to": "11861477",
#         "valid_tools": [1, 2]
#     },
#     "12885801092": {
#         "description": "white circle",
#         "translate_to": "10216663",
#         "valid_tools": [1]
#     },
#     "25779665946": {
#         "description": "white rectangle",
#         "translate_to": "10216663",
#         "valid_tools": [1, 2, 3, 4]
#     }
# }

class HardcodedRFIDs(Connection, threading.Thread):
    """
    This connection type is used when you have a list of hardcoded rfid tags.
    Really good for testing without a backend service.
    """
    def __init__(self, interlock, connection, config):
        """
        format: so far only json

        there is only one state to check, and it must be present: check_badge
        check_badge is a dictionary of states to switch to, followed by ":when",
        the content of the dictionary is a list of rfid tags.

        example config:

        "test_validation": {
            "type": "internal:hardcoded_rfids",
            "check_badge": {
                "error:maintenance:when": ["11505625070", "32885801092"],
                "active:when": ["21505625070", "12885801092"],
                "login_denied:when": ["default"],
            }
        }
        """
        threading.Thread.__init__(self)
        Connection.__init__(self, interlock, connection, config)

        log = logging.getLogger("HardcodedRFIDs.init")
        log.info("in HardcodedRFIDs.__init__()")
        
        #
        # we only care about "check_badge"
        #
        state_configs = {
                status: state_config
                for status, state_config in config.items()
                if status == MessageTypes.CHECK_BADGE}

        self.rfid_to_action_mapping = dict()
        for state, state_config in state_configs.items():
            error_prefix = connection + ": " + state + ": "
            log.info(connection + ": " + state + ", " +
                    "state_config: " + repr(state_config))
            for when_clause, rfid_listing in state_config.items():
                if when_clause.split(":")[-1] == "when":
                    action = ":".join(when_clause.split(":")[:-1])
                    for rfid in rfid_listing:
                        if rfid not in self.rfid_to_action_mapping:
                            self.rfid_to_action_mapping[rfid] = action
                        else:
                            log.error(error_prefix + rfid + 
                                    ": is in multiple when clauses, " +
                                    "configured to " + 
                                    self.rfid_to_action_mapping[rfid] )

    def update(self, action_message):
        status = action_message["state"]

        if status == MessageTypes.CHECK_BADGE:
            log = logging.getLogger("HardcodedRFIDs.update")
            error_prefix = self.connection + ": "

            new_state = None
            badge_id = action_message["badge_id"]
            if badge_id in self.rfid_to_action_mapping:
                new_state = self.rfid_to_action_mapping[badge_id]
            elif "default" in self.rfid_to_action_mapping:
                new_state = self.rfid_to_action_mapping["default"]

            if new_state:
                self.interlock.action_queue.put(
                    {"state": new_state,
                    "from": "HardcodedRFIDs.run()"})

            log.debug(error_prefix + ": returned from call")

################################################################################
#
#  Webservice Connection, and rfid validation
#
################################################################################

class WebServiceConnection(Connection, threading.Thread):
    """
    This connection type is used to connect with webservices.
    """
    def __init__(self, interlock, connection, config):
        """
        format: so far only json

        inside each state is is a webservice:
        url: the url which can be build, put {badge_id} and {tool_id} inside the
            url
        save_reply: set to true if we need the data from one reply to feed
            another url
        new_state: is a dictionary where the keys are the new states and their
            data is the returned data which must match the data from the url
            call.
        """
        threading.Thread.__init__(self)
        Connection.__init__(self, interlock, connection, config)

        log = logging.getLogger("WebServiceConnection.init")
        log.info("creating: " + connection)
        self.saved_reply = dict()

        self.run_state = None
        self.connection = connection
        self.interlock = interlock
        self.action_message = {}

        error_prefix = self.connection + ": "

        #
        # these are indexed by MessageTypes.ALL_STATES
        #
        self.state_to_actions = {}
        state_configs = {
                state: state_config
                for state, state_config in config.items()
                if state in MessageTypes.ALL_STATES}

        for state, state_config in state_configs.items():
            error = False
            error_prefix = connection + ": " + state + ": "
            log.info(connection + ": " + state + ", " +
                    "state_config: " + repr(state_config))

            if isinstance(state_config, dict):
                #
                # verify the presense of "url"
                #
                if 'url' not in state_config:
                    error = True
                    log.error(error_prefix + "url: missing")
                elif type(state_config['url']) != unicode:
                    error = True
                    log.error(error_prefix + "url: needs to be a string")
                else:
                    #
                    # default in save_reply
                    #
                    if 'save_reply' not in state_config:
                        state_config["safe_reply"] = False

            elif isinstance(state_config, unicode):
                #
                # We must have only be give a string, better be a url
                #
                state_config = {"url": state_config, "save_reply": False}
            else:
                #
                # not quite sure how to process this
                #
                error = True
                log.error(error_prefix + " not sure what to do with this: " +
                        repr(state_config))

            if not error:
                #
                # test for duplicate test conditions
                #
                test_conditions = [
                    test
                    for key, test in state_config.items()
                    if key[:-5] in MessageTypes.ALL_STATES]

                duplicate_test_conditions = [
                    test
                    for test in test_conditions
                    if test_conditions.count(test) > 1]

                if duplicate_test_conditions:
                    error = True
                    log.error(error_prefix +
                            "the following states have the same conditions: " +
                            ", ".join([duplicate_test_conditions.keys()]))

            if not error:
                #
                # looks like a valid config
                #
                if "save_reply" not in state_config:
                    state_config["save_reply"] = False
                self.state_to_actions[state] = state_config

        #
        # set up the task that monitors network connection and tool status
        #
        try:
            print "trying to start heartbeat_monitor on " + \
                    config["heartbeat_monitor"]["url"]
            self.network_heartbeat = NetworkHeartbeatMonitor(
                config["heartbeat_monitor"]["url"],
                self.interlock.action_queue)
            self.network_heartbeat.start()
            print "starting heartbeat_monitor on " + \
                    config["heartbeat_monitor"]["url"]
        except KeyError:
            self.network_heartbeat = None

        #
        # done with all processing, lets change our state to reflect that the
        # system is powered up
        #
        self.update({"state": MessageTypes.POWER_UP})

    def update(self, action_message):
        # print "ConnectionWebService: " + repr(action_message)
        if self.network_heartbeat:
            self.network_heartbeat.update(action_message)

        status = action_message["state"]

        if status in self.state_to_actions:
            log = logging.getLogger("WebServiceConnection.update")
            error_prefix = self.connection + ": "

            self.action_message = action_message
            self.run_state = self.state_to_actions[status]
            threading.Thread.__init__(self)
            self.start()

            log.debug(error_prefix + ": returned from call")

    def run(self):
        """
        This is used when we query the webservice so that we don't have to wait
        for the webservice query to complete when we make our query before
        updating the other connections.
        """
        log = logging.getLogger("WebServiceConnection.run")

        parms = self.run_state.copy()
        parms["tool_id"] = self.interlock.tool_id
        # print repr(self.action_message)

        for key, value in self.action_message.items():
            parms[key] = value

        for key, value in self.saved_reply.items():
            parms[key] = value

        # print repr(self.run_state['url'])
        # print repr(parms)
        json_response = ""
        try:
            url = self.run_state['url'].format(**parms)
            log.info("WebServiceConnection.run(): sent: " + url)
            json_response = urllib2.urlopen(url).readline()
            log.info("WebServiceConnection.run(): got: " + json_response)
        except KeyError:
            #
            # we don't care
            #
            pass
        except urllib2.HTTPError:
            msg = "WebServiceConnection.run(): Cannot contact " + url + \
                    " (HTTP)"
            self.interlock.action_queue.put({
                "state": MessageTypes.ERROR_NETWORK,
                "from": msg})
            log.error(msg)
        except urllib2.URLError:
            msg = "WebServiceConnection.run(): Cannot contact " + url + " (URL)"
            self.interlock.action_queue.put({
                "state": MessageTypes.ERROR_NETWORK,
                "from": msg})
            log.error(msg)

        try:
            response = json.loads(json_response)
            # print "lets parse " + repr(response)
            if self.run_state['save_reply']:
                self.saved_reply = response

            #
            # find which new state has the most matches
            #
            test_conditions = {
                    new_state[:-5]: condition
                    for new_state, condition in self.run_state.items()
                    if new_state[-5:] == ":when"}
            matched_conditions_count = 0
            matched_conditions_states = []
            for potential_new_state in test_conditions:
                conditions = test_conditions[potential_new_state]
                if all([response[key] == conditions[key]
                    for key in conditions]):

                    if len(conditions) == matched_conditions_count:
                        matched_conditions_states += [potential_new_state]

                    if len(conditions) > matched_conditions_count:
                        matched_conditions_states = [potential_new_state]
                        matched_conditions_count = len(conditions)

            if matched_conditions_count and len(matched_conditions_states) == 1:
                self.interlock.action_queue.put({
                    "state": matched_conditions_states[0],
                    "from": "ConnectionWebservice.run()"})
        except ValueError as error:
            # ValueError('No JSON object could be decoded',)
            print "WebServiceConnection.run(): " + repr(error)
            print "WebServiceConnection.run(): cannot process: json_reply: " + \
                    repr(json_response)
        except Exception as error:
            print "WebServiceConnection.run(): " + repr(error)

class NetworkHeartbeatMonitor(threading.Thread):
    """
    This is likely to go away, and be rolled int ConnectionWebService
    """
    states_to_remember = [
        MessageTypes.ACTIVE,
        MessageTypes.INACTIVE_SOON,
        MessageTypes.INACTIVE,
        MessageTypes.ERROR,
        MessageTypes.ERROR_CONFIG,
        MessageTypes.ERROR_NETWORK,
        MessageTypes.ERROR_MAINTENANCE
    ]
    states_to_check_makermanger = [
        MessageTypes.INACTIVE,
        MessageTypes.ERROR,
        MessageTypes.ERROR_NETWORK,
        MessageTypes.ERROR_MAINTENANCE
    ]

    def __init__(self, query_url, action_queue):
        """
        This is likely to go away, and be rolled int ConnectionWebService
        """
        threading.Thread.__init__(self)
        self.current_mode = MessageTypes.POWER_UP
        self.action_queue = action_queue
        self.query_url = query_url

    def update(self, action_message):
        """
        called from ConnectionWebService instead of main Interlock object
        """
        new_state = action_message["state"]
        if new_state in self.states_to_remember:
            self.current_mode = new_state

    def run(self):
        """
        This is the thread to watch the status of the url.
        """
        log = logging.getLogger("NetworkHeartbeatMonitor.run")
        log.info("start")
        error_prefix = "NetworkHeartbeatMonitor.run(): "
        while True:
            log.info("current_mode: " + self.current_mode)
            if self.current_mode in self.states_to_check_makermanger:
                errors = []
                errors_source = {}
                #
                # check the makermanager
                #
                try:
                    url = self.query_url.format(tool_id="", badge_id="")
                    log.info(error_prefix + "sent: " + url)
                    json_response = urllib2.urlopen(url).readline()
                    log.info(error_prefix + "got: " + json_response)
                    json.loads(json_response)

                except ValueError:
                    error_message = error_prefix + \
                            "makermanager is not returning valid JSON"
                    errors += [MessageTypes.ERROR_NETWORK]
                    errors_source[MessageTypes.ERROR_NETWORK] = error_message
                    log.error(error_message)

                except urllib2.HTTPError:
                    error_message = error_prefix + \
                            "Cannot contact makermanager (HTTP)"
                    errors += [MessageTypes.ERROR_NETWORK]
                    errors_source[MessageTypes.ERROR_NETWORK] = error_message
                    log.error(error_message)

                except urllib2.URLError:
                    error_message = error_prefix + \
                            "Cannot contact makermanager (URL)"
                    errors += [MessageTypes.ERROR_NETWORK]
                    errors_source[MessageTypes.ERROR_NETWORK] = error_message
                    log.error(error_message)

                #
                # check the maintenance status
                #

                #
                # update status as necessary
                #
                if not errors:
                    if self.current_mode != MessageTypes.INACTIVE:
                        #
                        # no longer have errors, let everyone know !
                        #
                        self.action_queue.put({
                            "state": MessageTypes.INACTIVE,
                            "from": error_prefix + "found network"})
                    #
                    # no problems, lets check again in 30 seconds so as not to
                    # irritate the server too much
                    #
                    time.sleep(30)
                elif self.current_mode not in errors:
                    #
                    # if the current error state is not in the current list of
                    # errors then make take the first error
                    #
                    use_error = errors[0]
                    self.action_queue.put({
                        "state": use_error,
                        "from": errors_source[use_error]})
                    time.sleep(1)
            else:
                #
                # we're busy doing stuff, no point checking the network
                # connection
                #
                time.sleep(.5)

################################################################################
#
#  RGB backlight LCD over SPI Connection
#
################################################################################

class LcdP018Output(Connection, threading.Thread):
    """
    This output class updates a p018 display, which is a pic controller
    listening to an i2c bus and updating an lcd display with rgb led
    backlight.
    """
    def __init__(self, interlock, connection, config):
        """
        """
        threading.Thread.__init__(self)
        Connection.__init__(self, interlock, connection, config)

        log = logging.getLogger("LcdP018Output.init")
        log.info("creating: " + connection)
        self.mode = None
        self.lcd = None
        self.timer = None
        self.saved_status = None

        error_prefix = connection + ": "

        valid_i2c_ports = ("i2c:0:0x38", "i2c:1:0x38")
        if connection not in valid_i2c_ports:
            log.error(error_prefix + "should be: " + ", ".join(valid_i2c_ports))
        else:
            self.i2c_bus_number = int(connection.split(":")[1])
            self.lcd = lcd_i2c_p018.lcd(self.i2c_bus_number)

        #
        # these are indexed by MessageTypes.ALL_STATES
        #
        self.state_to_actions = {}
        state_configs = {
                state: state_config
                for state, state_config in config.items()
                if state in MessageTypes.ALL_STATES}

        for state, state_config in state_configs.items():
            error_prefix = connection + ": " + state + ": "
            log.info(connection + ": " + state + ", " +
                    "state_config: " + repr(state_config))

            if isinstance(state_config, dict):
                #
                # process more complex configuration, such as:
                #    "active": {
                #               "color":   (0, 255, 255),
                #        "message": ["line 1 message", "line 2 message"]
                #        "timeout": 3,
                #    }
                #
                # timeout specifies how many seconds to stay on before going
                # back to the previous message
                #

                #
                # get the color
                #
                action = {
                    "message": [" -- oo OO oo -- ", " -- oo OO oo -- "],
                    "color":     (128, 128, 128),
                    "timeout": None
                }
                if 'message' not in state_config:
                    log.error(error_prefix + "message: missing")
                elif (type(state_config['message']) != list or
                        len(state_config['message']) != self.lcd.rows or
                        len([len(message)
                              for message in state_config['message']
                              if len(message) != self.lcd.columns]) > 0):
                    log.error(error_prefix +
                            "message: needs to be an array of " +
                            repr(self.lcd.rows) + " strings of " +
                            repr(self.lcd.columns) + " characters")
                else:
                    action["message"] = state_config['message']

                #
                # get the color
                #
                if 'color' not in state_config:
                    log.error(error_prefix + "color: missing")
                elif (type(state_config['color']) != list or
                        len(state_config['color']) != 3 or
                        len([element for element in state_config['color']
                            if type(element) not in (int, float)]) or
                        len([number for number in state_config['color']
                            if number > 255 or number < 0])):
                    log.error(error_prefix + "color: needs to be " +
                            "a tuple of 3 numbers between 0 and 255")
                else:
                    action["color"] = state_config['color']

                #
                # get the timeout
                #
                try:
                    timeout = float(state_config['timeout'])
                    log.info(error_prefix + ": timeout:" + repr(timeout))
                except KeyError:
                    timeout = None
                    log.info(error_prefix + ': timeout defaulting to "always"')
                except ValueError:
                    timeout = None
                    log.error(error_prefix + state_config['timeout'] +
                            " needs to be a float or an int")
                action["timeout"] = timeout

                self.state_to_actions[state] = action
            else:
                #
                # not quite sure how to process this
                #
                log.error(error_prefix + repr(state_config) + \
                    ": should be one of: " + \
                    ", ".join(self.state_to_actions.keys()))
        #
        # done with all processing, lets change our state to reflect that the
        # system is powered up
        #
        self.update({"state": MessageTypes.POWER_UP})

    def update(self, action_message):
        """
        call with one of these parameters:
        : ACTIVE
        : INACTIVE_SOON
        : INACTIVE
        """
        status = action_message["state"]

        log = logging.getLogger("LcdP018Output.update")
        log.info(repr(self.i2c_bus_number) + " gets " +  status)

        if status in self.state_to_actions:
            log.info(repr(self.i2c_bus_number) + " displays " +  status)
            action = self.state_to_actions[status]

            for attr in ['color', 'message', 'timeout']:
                log.debug(": ".join([
                    repr(self.i2c_bus_number), attr, repr(action[attr])]))

            self.lcd.show_rgb(action['message'], action['color'])

            if self.timer != None:
                self.timer.cancel()

            if action['timeout']:
                self.timer = threading.Timer(
                        action['timeout'], self.reset_message)
                self.timer.start()
            elif status not in MessageTypes.INFO_ONLY:
                self.saved_status = status

            log.debug(repr(self.i2c_bus_number) + ": returned from call")

        else:
            log.info("nothing configured")

    def reset_message(self):
        """
        Set the message back to the more recent non-transient state
        """
        if self.saved_status != None:
            action = self.state_to_actions[self.saved_status]
            self.lcd.show_rgb(action['message'], action['color'])


################################################################################
#
#  digital gpio Connection
#
################################################################################

class DigitalOutput(Connection, threading.Thread):
    """
    control the works with digital output
    """

    def __init__(self, interlock, connection, config):
        """
        """
        threading.Thread.__init__(self)
        Connection.__init__(self, interlock, connection, config)

        log = logging.getLogger("DigitalOutput.init")
        log.info("creating: " + connection)

        #
        # figure out what to do with this pin for all states
        #
        self.control_pin = connection
        self.timer = None
        self.blink_time = None

        #
        # do we want a GPIO.HIGH or GPIO.LOW to turn it "on"
        #
        if config.get("on", "HIGH") == "LOW":
            self._on = GPIO.LOW
            self.off = GPIO.HIGH
        else:
            self._on = GPIO.HIGH
            self.off = GPIO.LOW

        #
        # put one level lower ?
        #
        action_to_function = {
                "OFF":   self.turn_off,
                "ON":    self.turn_on,
                "BLINK": self.blink,
                "SOS":   self.sos
        }

        #
        # these are indexed by MessageTypes.ALL_STATES
        #
        self.state_to_actions = {}
        state_configs = {
                state: state_config
                for state, state_config in config.items()
                if state in MessageTypes.ALL_STATES}

        for state, state_config in state_configs.items():
            error_prefix = connection + ": " + state + ": "
            log.info(connection + ": " + state + ", " +
                    "state_config: " + repr(state_config))

            if isinstance(state_config, dict):
                #
                # process more complex configuration, such as:
                #    "active": {
                #        "output": "ON",
                #        "seconds": 3,
                #
                if 'output' not in state_config:
                    log.error(error_prefix + "output: missing")
                elif state_config['output'] in action_to_function:
                    function = action_to_function[state_config['output']]
                    try:
                        seconds = float(state_config['seconds'])
                        self.state_to_actions[state] = {
                                "function": function, "parameter": seconds}
                        log.info(error_prefix + ": seconds:" + repr(seconds))
                    except KeyError:
                        seconds = None
                        self.state_to_actions[state] = {
                                "function": function, "parameter": seconds}
                        log.info(error_prefix +
                                ': seconds defaulting to "always"')
                    except ValueError:
                        seconds = None
                        log.error(error_prefix + repr(state_config['seconds']) +
                                " needs to be a float or an int")
                else:
                    log.error(error_prefix + "output: " +
                            state_config['output'] +
                            ": should be one of: " +
                            ", ".join(action_to_function.keys()))
            elif state_config in action_to_function:
                #
                # process simple configuration, such as:
                #    "active": "ON"
                #
                function = action_to_function[state_config]
                self.state_to_actions[state] = {
                        "function": function, "parameter": None}
            else:
                #
                # not quite sure how to process this
                #
                log.error(error_prefix + repr(state_config) +
                            ": should be one of: " +
                            ", ".join(action_to_function.keys()))

        GPIO.setup(self.control_pin, GPIO.OUT)
        log.info(self.control_pin + "): state actions are: " +
                ", ".join(self.state_to_actions))
        #
        # done with all processing, lets change our state to reflect that this
        # pin is inactive
        #
        self.update({"state": MessageTypes.INACTIVE})

    def update(self, action_message):
        """
        call with one of these parameters:
        : ACTIVE
        : INACTIVE_SOON
        : INACTIVE
        """
        status = action_message["state"]

        log = logging.getLogger("DigitalOutput.update")
        log.info(self.control_pin + " gets " +  status)

        if status in self.state_to_actions:
            log.info(self.control_pin + " gets " +  status)
            # print repr(self.state_to_actions[status])
            #    self.state_to_actions[state] =
            #        {"function": function, "parameter": seconds}

            action = self.state_to_actions[status]

            log.debug(self.control_pin + ": action[parameter]: " +
                    repr(action['parameter']))
            log.debug(self.control_pin + ": action.keys(): " +
                    repr(action.keys()))

            function = action['function']
            parameter = action['parameter']
            if parameter != None:
                function(parameter)
            else:
                function()
            log.debug(self.control_pin + ": returned from call")

        elif status == "ERROR":
            log.info(self.control_pin + ": found ERROR to do")
            self.sos()
        else:
            log.info("nothing configured")

    def turn_on(self, seconds=None):
        """
        turn the line on, taking into account whether it is HIGH or LOW on
        """
        log = logging.getLogger("DigitalOutput.turn_on")
        log.info(self.control_pin + ": seconds: " + repr(seconds))
        self.clear_threads()
        if seconds == None:
            GPIO.output(self.control_pin, self._on)
            self.timer = None
        else:
            GPIO.output(self.control_pin, self._on)
            self.timer = threading.Timer(seconds, self.turn_off)
            # lambda: GPIO.output(self.control_pin, self.off))
            log.debug(self.control_pin + ": starting timer")
            self.timer.start()

    def turn_off(self, seconds=None):
        """
        turn the line off, taking into account whether it is HIGH or LOW on
        """
        log = logging.getLogger("DigitalOutput.turn_off")
        log.info(self.control_pin + ": (" + repr(seconds) + ")")
        self.clear_threads()
        if seconds == None:
            GPIO.output(self.control_pin, self.off)
        else:
            self.timer = threading.Timer(seconds, self.turn_on)
            log.debug(self.control_pin + ": starting timer")
            self.timer.start()

    def blink(self, seconds=.5):
        """
        make the digital line blink, the interval can be passed in, or defaults
        to a blink per second
        """
        log = logging.getLogger("DigitalOutput.blink")
        log.info(self.control_pin + ": (" + repr(seconds) + ")")
        self.clear_threads()
        self.blink_time = seconds
        threading.Thread.__init__(self)
        self.start()

    def sos(self, seconds=None):
        """
        make the digital line blink SOS in morese code
        """
        log = logging.getLogger("DigitalOutput.sos")
        log.info(self.control_pin + ": (" + repr(seconds) + ")")
        self.clear_threads()
        self.blink_time = "sos"
        self.start()

    def run(self):
        """
        This is used when we blink the output
        """
        log = logging.getLogger("DigitalOutput.run")
        log.info(self.control_pin + ": (" + repr(self.blink_time) + ")")
        while self.blink_time != None:
            if self.blink_time == "sos":
                self.run_sos()
            else:
                self.run_blink()

    def run_blink(self):
        """
        this is the task which actually blinks the digitial output
        """
        log = logging.getLogger("DigitalOutput.blink")
        log.info(self.control_pin + ": cycle time: " + repr(self.blink_time))
        blink_high = True
        while self.blink_time != None:
            GPIO.output(self.control_pin,
                    {True: self._on, False: self.off}[blink_high])
            blink_high = not blink_high
            time.sleep(self.blink_time)

    def run_sos(self):
        """
        this is the task which makes the digitial output pulse SOS
        """
        log = logging.getLogger("DigitalOutput.sos")
        log.info(self.control_pin)
        sequence = [
                (.3, self._on), (.3, self.off),
                (.3, self._on), (.3, self.off),
                (.3, self._on),

                (1, self.off),

                (1, self._on), (.3, self.off),
                (1, self._on), (.3, self.off),
                (1, self._on),

                (1, self.off),

                (.3, self._on), (.3, self.off),
                (.3, self._on), (.3, self.off),
                (.3, self._on),

                (2, self.off),
        ]

        index = 0
        while self.blink_time == "sos":
            seconds, value = sequence[index]
            GPIO.output(self.control_pin, value)
            time.sleep(seconds)

            index += 1
            index = 0 if index >= len(sequence) else index

    def clear_threads(self):
        """
        turn off the threads which are blinking the
        """
        if self.timer != None:
            self.timer.cancel()
        self.blink_time = None

################################################################################
#
#  stdio Connection
#
################################################################################

class StdioOutput(Connection):
    """
    show our current state on stdout
    """

    def __init__(self, interlock, connection, config):
        """
        the config is a dictionary where the dictionary keys are the states and
        the values are which string to print on stdout
        """
        Connection.__init__(self, interlock, connection, config)

        log = logging.getLogger("StdioOutput.init")
        log.info(connection)
        #
        # these are indexed by MessageTypes.ALL_STATES
        #
        # print config
        self.state_actions = {}
        state_configs = {
                status: state_config
                for status, state_config in config.items()
                if status in MessageTypes.ALL_STATES}

        for status, state_config in state_configs.items():
            log.info("adding " + repr(status) + " as " + repr(state_config))
            self.state_actions[status] = repr(state_config)
        #
        # done with all processing, lets change our state to reflect that the
        # system is powered up
        #
        self.update({"state": MessageTypes.POWER_UP})


    def update(self, action_message):
        """
        call with any of the valid states to get the configured message
        """
        status = action_message["state"]

        if status in self.state_actions:
            print self.state_actions[status]

################################################################################
#
#  generic Monitor
#
################################################################################

class Monitor(threading.Thread, Connection):
    """
    This is a generic class which monitors the state of something of interest,
    such as a digitial input or analog input put, and changes the state of the
    interlock depending on the current state and the input
    """
    def __init__(self, interlock, connection, config):
        """
        Override to provide your own config parser
        """
        Connection.__init__(self, interlock, connection, config)
        threading.Thread.__init__(self)
        self.run_continuously = True


################################################################################
#
#  digital Monitor
#
################################################################################
class DigitalMonitor(Monitor):
    """
    Monitor digitial gpio here which triggers activity when the line goes high
    or low.
    """
    def __init__(self, interlock, connection, config):
        """
        We can only notice if the signal is FALLING or RISING.
        """
        log = logging.getLogger("DigitalMonitor.init")

        Monitor.__init__(self, interlock, connection, config)

        GPIO.setup(self.connection, GPIO.IN)

        #
        # read in the configuration
        #
        triggers = ["FALLING", "RISING"]
        self.trigger_to_new_state = {
                trigger: status
                for status, trigger in config.items()
                if status in MessageTypes and trigger in triggers}

        log.info(self.connection + ": " + repr(self.trigger_to_new_state))

    def run(self):
        """
        this is the process that actually notices when the state of the digital
        gpio changes and submits a state change request.
        """
        log = logging.getLogger("DigitalMonitor.run")
        while True:
            if GPIO.input(self.connection):
                GPIO.wait_for_edge(self.connection, GPIO.FALLING)
                message = self.trigger_to_new_state.get("FALLING")
            else:
                GPIO.wait_for_edge(self.connection, GPIO.RISING)
                message = self.trigger_to_new_state.get("RISING")

            if message:
                packet = {"state": message,
                        "from": "DigitalMonitor: " + self.connection}
                log.info(self.connection + ': sending ' + repr(packet))
                self.interlock.action_queue.put(packet)


################################################################################
#
#  adc Monitor
#
################################################################################
class AnalogMonitor(Monitor):
    """
    This class if for setting states depending on whether a voltage goes high,
    low, inside a range, or outside a range
    """
    def __init__(self, interlock, connection, config):
        """
        connection is one of:
        AIN0, AIN1, AIN2, AIN3, AIN4, AIN5

        config is a dictionary where the key is the new state, and its value
        is a dictionary where the key is either "higher", or "lower" followed by
        the value read in where the value read in is 0 thru 1 which maps to
        0 volts to 1.8 volts on the ADC line.
        """
        Monitor.__init__(self, interlock, connection, config)

        self.message_conditions = dict()
        state_configs = {
                state: state_config
                for state, state_config in config.items()
                if state in MessageTypes.ALL_STATES and
                    type(state_config) == dict}

        for state, state_config in state_configs:
            conditions = {}
            for key in ['higher', 'lower']:
                try:
                    conditions[key] = float(state_config.get(key))
                except KeyError:
                    pass
                except TypeError:
                    pass

            conditions['evaluate'] = "or"
            if "higher" in conditions and "lower" in conditions:
                if conditions['higher'] < conditions['lower']:
                    #
                    # in other words, we are specifying a range
                    #
                    conditions['evaluate'] = "and"
            if conditions:
                self.message_conditions[state] = conditions

        ADC.setup()

    def run(self):
        """
        This is the process which checkes the analog in pin to see if the
        line goes too or too low.
        """
        ADC.read(self.connection)
        while True:
            time.sleep(.01)
            value = ADC.read(self.connection)
            for message, conditions in self.message_conditions.items():
                if conditions['evaluate'] == "and":
                    trigger = True
                    if 'higher' in conditions:
                        trigger &= value > conditions['higher']
                    if 'lower' in conditions:
                        trigger &= value < conditions['lower']
                else:
                    trigger = False
                    if 'higher' in conditions:
                        trigger |= value > conditions['higher']
                    if 'lower' in conditions:
                        trigger |= value < conditions['lower']
                if trigger:
                    self.interlock.action_queue.put({
                        "state": message,
                        "from": "DigitalMonitor: " + self.connection})
                    time.sleep(.5)

################################################################################
#
#  The Interlock
#
################################################################################

class Interlock(threading.Thread):
    """
    the is the main Interlock class used to insure that people have permission
    to use this tool.  It keeps track of timeing and lets all of the connections
    know about the current state.
    """

    def __init__(self, interlock_config, error_log):
        """
        Pass in the master config which also contains all the configuration
        for the connections for this RFID Interlock installation
        """
        log = logging.getLogger("Interlock.init")
        log.info("in interlock.__init__")

        #
        # this is where all errors get logged
        #
        self.error_log = error_log

        #
        # start our threaded environment that we require
        #
        threading.Thread.__init__(self)
        self.action_queue = Queue.Queue()
        try:
            self.timeout = int(interlock_config.get('timeout', 0))
        except ValueError:
            log.error("timeout is: " + interlock_config['timeout'] +
                    " needs to be a float or int")

        try:
            self.warning_seconds = int(interlock_config.get('warning', 0))
        except ValueError:
            log.error("warning is: " + interlock_config['warning'] +
                    " needs to be float or int")

        self.timer_to_warning = None
        self.timer_to_deactivate = None

        #
        # get the tool id
        #
        if interlock_config.get('tool_id', "") == "":
            self.tool_id = hex(get_mac_address())[2:-1]
        else:
            self.tool_id = interlock_config['tool_id']

        #
        # process connections
        #
        connection_mapping = {
            "digital:output":           DigitalOutput,
            "stdio:output":             StdioOutput,
            "lcd_p018:output":          LcdP018Output,
            "webservice:connection":    WebServiceConnection,
            "serial:badge_reader":      SerialBadgeReader,
            "stdio:badge_reader":       KeyboardBadgeReader,
            "input_event:badge_reader": InputEventBadgeReader,
            "analog:monitor":           AnalogMonitor,
            "digital:monitor":          DigitalMonitor,
            "internal:hardcoded_rfids": HardcodedRFIDs,
        }
        self.connections = []

        for connection_name, connection_config in interlock_config.items():
            if type(connection_config) == dict and \
                    "type" in connection_config and \
                    connection_config['type'] in connection_mapping:
                # try:
                connection = connection_mapping[connection_config['type']](
                        self, connection_name, connection_config)
                self.connections.append(connection)
                # if isinstance(connection, Monitor) or \
                #         isinstance(connection, BadgeReader):
                if connection.run_continuously:
                    connection.start()
                log.info("connection " + connection_name + " added")
                print "connection " + connection_name + " added"
                # except Exception as error:
                # log.error("connection " + connection_name + 
                # " could not be added: " +
                #         repr(error.message) + repr(error.args))
        print "finished initialziing " + str(len(self.connections)) + \
                " connections"
                   
    def run(self):
        """
        This is the task which is run for the Interlock, this is like a job
        scheduler that you will find in most modern operating systems.
        """
        # print "run forest run!"

        log = logging.getLogger("Interlock.run")
        log.debug("starting")

        #
        #  status_update_actions is to replace a case statement.  It maps the
        #  message types to internal to internal functions that need to be
        #  called to perform internal housekeeping, mostly to keep up with
        #  timing requirements
        #
        status_update_actions = {
            MessageTypes.ACTIVE:            self.active_mode,
            MessageTypes.INACTIVE_SOON:     self.warning_mode,
            MessageTypes.INACTIVE:          self.inactive_mode,
            MessageTypes.RESET_TIMER:       self.reset_timers,
            MessageTypes.ERROR:             self.error
        }

        self.action_queue.put({
            "state": MessageTypes.INACTIVE,
            "from": "Interlock.run() initial power up"})

        while True:
            log.debug("waiting on action_queue.get()")
            message = self.action_queue.get()
            print message
            new_state = message.get("state")
            queued_from = message.get("from")

            log.debug("setting status to {0} because {1} said so".format(
                    new_state, queued_from))

            #
            # perform internal housekeeping as a due to the message in the queue
            #
            # print "do internal housekeeping"
            if new_state in status_update_actions:
                status_update_actions[new_state]()

            #
            # let all of the connections know of the new state from the message
            # in the queue
            #
            # for update_me in self.need_status_updates:
            # print "tell " + str(len(self.connections)) + " connections"
            for connection in self.connections:
                # print "telling:"
                # print update_me
                connection.update(message)
            # print "told everyone"

        log.debug("ending")

    def locked_out(self):
        """
        Tragic errors, cannot do anything.
        """
        # for update_me in self.need_status_updates:
        for update_me in self.connections:
            update_me.update({"state": MessageTypes.ERROR_CONFIG})

    def active_mode(self):
        """
        We have just activated the tool, set up a timer to wake up whenever
        we are about ready to turn the tool off
        """
        log = logging.getLogger("Interlock.run")
        log.debug("active_mode start")

        self.clear_all_timers()

        self.timer_to_warning = threading.Timer(
                self.timeout - self.warning_seconds,
                lambda: self.action_queue.put({
                    "state": MessageTypes.INACTIVE_SOON,
                    "from": "Interlock.active_mode()"}))

        log.debug("active_mode starting timers")
        self.timer_to_warning.start()
        log.debug("active_mode end")


    def warning_mode(self):
        """
        We have just about ready to turn the tool off, set up a timer to wake
        us up whenever it is time to deactivate the tool
        """
        log = logging.getLogger("Interlock.run")
        log.debug("warning_mode")

        if self.timer_to_deactivate != None and self.timer_to_warning == None:
            #
            # already in warning mode
            #
            pass
        else:
            self.clear_all_timers()
            self.timer_to_deactivate = threading.Timer(
                    self.warning_seconds,
                    lambda: self.action_queue.put(({
                        "state": MessageTypes.INACTIVE,
                        "from": "Interlock.active_mode()"})))
            self.timer_to_deactivate.start()

    def inactive_mode(self):
        """
        the tool is off, turn off all timers
        """
        log = logging.getLogger("Interlock.run")
        log.debug("inactive_mode() called")

        self.clear_all_timers()

    def reset_timers(self):
        """
        Clear the timers.  One call does it all.
        """
        log = logging.getLogger("Interlock.run")
        log.debug("reset_timers called")

        if self.timer_to_warning != None or self.timer_to_deactivate != None:
            self.action_queue.put({
                "state": MessageTypes.ACTIVE,
                "from": "Interlock.reset_timers()"})

    def error(self):
        """
        error mode.  Clear the timers.
        """
        log = logging.getLogger("Interlock.run")
        log.debug("errors called")
        self.clear_all_timers()

    def clear_all_timers(self):
        """
        time to clear the deactivation timer and the deactivation soon timer
        """
        if self.timer_to_warning != None:
            self.timer_to_warning.cancel()
            self.timer_to_warning = None
        if self.timer_to_deactivate != None:
            self.timer_to_deactivate.cancel()
            self.timer_to_deactivate = None

def run_from_commandline():
    """
    This sets up the data structures required to run the RFID interlock.
    Look in the Interlock class, the run() method for the loop that keeps things
    going, and updated.
    """
    #
    # Insure that we are the only instance running, yes, this is very unix
    #
    lock_filename = "/var/lock/muther_rfid"
    lock_file = open(lock_filename, "w+")
    try:
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.truncate(0)
        lock_file.write(str(os.getpid()))
    except IOError:
        print "Another instance is still running"
        sys.exit(0)

    #
    # read in the configuration file that defines what we do
    #
    config = configuration.use_file("/etc/muther.ini")
    config = configuration.read()

    #
    # set up logging
    #
    error_log = ErrorArrayHandler()
    error_log.setLevel(logging.ERROR)

    logging.config.dictConfig(config.get('logging', {}))
    logger = logging.getLogger()
    logger.addHandler(error_log)
    logger.setLevel(logging.DEBUG)

    #
    # let's do this thing
    #
    interlock = Interlock(config, error_log)
    if error_log.get_errors():
        print "here are the errors"
        for init_error in error_log.get_errors():
            print ":  ".join([
                init_error.levelname, init_error.name, init_error.message])
        interlock.locked_out()
    else:
        interlock.start()

################################################################################
#
#  command line initiation
#
################################################################################

if __name__ == "__main__":
    run_from_commandline()
