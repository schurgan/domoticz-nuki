"""
<?xml version="1.0" encoding="UTF-8"?>
<plugin key="NukiLock" name="Nuki Lock Plugin" author="heggink" version="1.0.7-fixed">
    <description>
        <h2>Nuki Lock Plugin</h2>
        <p>Domoticz HTTP support for Nuki locks via Nuki Bridge (developer mode).</p>
        <p>Locks are Units 1..N, Unlatch buttons are Units N+1..2N (no collisions).</p>
    </description>

    <params>
        <param field="Port"  label="Callback Port (Domoticz listens on)" width="160px" required="true" default="8008"/>
        <param field="Mode1" label="Bridge IP" width="180px" required="true" default="192.168.1.123"/>
        <param field="Mode2" label="Bridge token" width="220px" required="true" default="abcdefgh"/>
        <param field="Mode4" label="Bridge port" width="120px" required="true" default="8080"/>
        <param field="Mode3" label="Poll interval (m)" width="120px" required="true" default="10"/>
        <param field="Mode5" label="Token Mode" width="120px">
           <options>
               <option label="Hashed" value="Hashed" />
               <option label="Plain" value="Plain" default="true"/>
           </options>
        </param>
        <param field="Mode6" label="Logging" width="140px">
            <options>
                <option label="Debug" value="Debug"/>
                <option label="Normal" value="Normal" default="true" />
                <option label="File" value="File"/>
            </options>
        </param>
    </params>
</plugin>
"""
#  nuki python plugin (fixed)
#
# Author: heggink/schurgan, 2025 (with fixes)
#
# Fixes:
# - Unlatch unit numbering moved to N+1..2N (no unit collisions)
# - Callback listener now ALWAYS starts (also after callback add)
# - HTTPException import fixed
# - Port types fixed (int for listen port)
# - onStop safe
# - LogMessage logic corrected
#
import Domoticz
import json
import socket
import urllib.request
import urllib.error
from urllib.error import URLError, HTTPError
from http.client import HTTPException

nukiHashDisabled = False
try:
    from random import randrange
    from hashlib import sha256
    from datetime import datetime
except Exception:
    nukiHashDisabled = True


class BasePlugin:
    enabled = False
    httpServerConn = None
    httpServerConns = {}
    httpClientConn = None
    heartbeats = 0
    pollInterval = 0
    bridgeIP = ' '
    bridgeToken = ' '
    callbackPort = 0
    bridgePort = 0
    hashedToken = False
    myIP = ' '
    numLocks = 0
    lockNames = []
    lockIds = []

    def __init__(self):
        return

    def generateTokenString(self):
        tokenStr = ""
        if self.hashedToken:
            ts = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            rnr = randrange(65535)
            hashnum = sha256(str('{},{},{}').format(ts, rnr, self.bridgeToken).encode('utf-8')).hexdigest()
            tokenStr = str('ts={}&rnr={}&hash={}').format(ts, rnr, hashnum)
        else:
            tokenStr = str('token=') + self.bridgeToken
        return tokenStr

    def onStart(self):
        if Parameters["Mode6"] != "Normal":
            Domoticz.Debugging(1)
        DumpConfigToLog()

        # Parameters
        self.callbackPort = int(Parameters["Port"])
        self.bridgeIP = Parameters["Mode1"]
        self.bridgeToken = Parameters["Mode2"]
        self.pollInterval = int(Parameters["Mode3"])
        self.bridgePort = str(Parameters["Mode4"])
        self.hashedToken = bool(Parameters["Mode5"] == "Hashed")

        if (nukiHashDisabled and self.hashedToken):
            self.hashedToken = False
            Domoticz.Error('Missing imports for Hashed token generation - Falling back to Plain')

        # Determine local IP (for callback URL)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        self.myIP = s.getsockname()[0]
        s.close()
        Domoticz.Debug("My IP is " + self.myIP)
        Domoticz.Log("Nuki plugin started on IP " + self.myIP + " and port " + str(self.callbackPort))

        # List locks
        req = 'http://' + self.bridgeIP + ':' + self.bridgePort + '/list?' + self.generateTokenString()
        Domoticz.Debug('REQUESTING ' + req)

        try:
            resp_raw = urllib.request.urlopen(req).read()
        except HTTPError as e:
            Domoticz.Error('NUKI HTTPError code: ' + str(e.code))
            return
        except URLError as e:
            Domoticz.Error('NUKI URLError Reason: ' + str(e.reason))
            return
        else:
            strData = resp_raw.decode("utf-8", "ignore")
            Domoticz.Debug("Lock list received " + strData)
            resp = json.loads(strData)

        num = len(resp)
        Domoticz.Debug("I count " + str(num) + " locks")
        self.numLocks = num

        # Reset lists on restart
        self.lockNames = []
        self.lockIds = []

        # Create lock device(s): Units 1..N
        for i in range(num):
            lock_unit = i + 1
            if (lock_unit not in Devices):
                Domoticz.Device(Name=resp[i]["name"], Unit=lock_unit, TypeName="Switch", Switchtype=19, Used=1).Create()
                Domoticz.Log("Lock " + resp[i]["name"] + " created.")
            else:
                Domoticz.Debug("Lock " + resp[i]["name"] + " already exists.")

            self.lockNames.append(resp[i]["name"])
            self.lockIds.append(resp[i]["nukiId"])

            batt = 0 if resp[i]["lastKnownState"]["batteryCritical"] else 255

            nval = -1
            sval = "Unknown"
            if (resp[i]["lastKnownState"]["state"] == 1):
                sval = 'Locked'
                nval = 1
            elif (resp[i]["lastKnownState"]["state"] == 3):
                sval = 'Unlocked'
                nval = 0

            Devices[lock_unit].Update(nValue=nval, sValue=str(sval),
                                      Description=str(resp[i]["nukiId"]), BatteryLevel=batt)

        # Create unlatch device(s): Units N+1..2N  (FIXED: no collisions)
        for i in range(num):
            unlatch_unit = num + (i + 1)
            if (unlatch_unit not in Devices):
                Domoticz.Device(Name=resp[i]["name"] + " Unlatch",
                                Unit=unlatch_unit, TypeName="Switch",
                                Switchtype=9, Used=1).Create()
                Domoticz.Log("Unlatch for Lock " + resp[i]["name"] + " created.")
            else:
                Domoticz.Debug("Unlatch for Lock " + resp[i]["name"] + " already exists.")

        Domoticz.Debug("Lock(s) created")
        DumpConfigToLog()

        # Check callbacks
        req = 'http://' + self.bridgeIP + ':' + self.bridgePort + '/callback/list?' + self.generateTokenString()
        Domoticz.Debug('checking callback ' + req)
        found = False

        try:
            resp_raw = urllib.request.urlopen(req).read()
        except HTTPError as e:
            Domoticz.Error('NUKI HTTPError code: ' + str(e.code))
        except URLError as e:
            Domoticz.Error('NUKI URLError Reason: ' + str(e.reason))
        except HTTPException as e:
            Domoticz.Error('NUKI HTTPException: ' + str(e))
        else:
            strData = resp_raw.decode("utf-8", "ignore")
            Domoticz.Debug("Callback list received " + strData)
            resp_cb = json.loads(strData)
            urlNeeded = 'http://' + self.myIP + ':' + str(self.callbackPort)
            callbacks = resp_cb.get("callbacks", [])
            Domoticz.Debug("Found callbacks: " + str(len(callbacks)))
            for cb in callbacks:
                if cb.get("url") == urlNeeded:
                    Domoticz.Debug("Callback already installed")
                    found = True
                    break

        if not found:
            callback = ('http://' + self.bridgeIP + ':' + self.bridgePort +
                        '/callback/add?' + self.generateTokenString() +
                        '&url=http%3A%2F%2F' + self.myIP + '%3A' + str(self.callbackPort))
            Domoticz.Log('Installing callback ' + callback)

            try:
                resp_raw = urllib.request.urlopen(callback).read()
            except HTTPError as e:
                Domoticz.Error('NUKI HTTPError code: ' + str(e.code))
            except URLError as e:
                Domoticz.Error('NUKI URLError Reason: ' + str(e.reason))
            else:
                strData = resp_raw.decode("utf-8", "ignore")
                Domoticz.Debug("Callback response received " + strData)
                resp_add = json.loads(strData)
                if resp_add.get("success", False):
                    Domoticz.Log("Nuki Callback install succeeded")
                else:
                    Domoticz.Error("Unable to register NUKI callback")

        # FIX: Always start listening for callbacks (even after adding callback)
        self.httpServerConn = Domoticz.Connection(
            Name="Server Connection", Transport="TCP/IP", Protocol="HTML", Port=self.callbackPort
        )
        self.httpServerConn.Listen()

        Domoticz.Debug("Leaving on start")

    def onStop(self):
        try:
            if self.httpServerConn is not None:
                self.httpServerConn = None
        except Exception:
            pass

    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Log("Connected successfully to: " + Connection.Address + ":" + Connection.Port)
        else:
            Domoticz.Log("Failed to connect (" + str(Status) + ") to: " + Connection.Address + ":" + Connection.Port +
                         " with error: " + Description)
        Domoticz.Log(str(Connection))
        if (Connection != self.httpClientConn):
            self.httpServerConns[Connection.Name] = Connection

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called for connection: " + Connection.Address + ":" + Connection.Port)
        strData = Data.decode("utf-8", "ignore")
        Domoticz.Debug("Lock message received " + strData)

        try:
            Response = strData[strData.index('{'):]
            Domoticz.Debug("JSON is " + Response)
            Response = json.loads(Response)
        except Exception as e:
            Domoticz.Error("Failed parsing callback JSON: " + str(e))
            return

        lock_id = Response.get("nukiId")
        if lock_id not in self.lockIds:
            Domoticz.Error("Unknown lock id in callback: " + str(lock_id))
            return

        foundlock = self.lockIds.index(lock_id)
        batt = 10 if Response.get("batteryCritical", False) else 255

        Domoticz.Log(self.lockNames[foundlock] + " requests update: " + str(Response.get("stateName", "")))

        if (Response.get("state") == 1):
            UpdateDevice(foundlock + 1, 1, "Locked", batt)
        elif (Response.get("state") == 3):
            UpdateDevice(foundlock + 1, 0, "Unlocked", batt)
        elif (Response.get("state") == 0):
            Domoticz.Error("Nuki lock " + self.lockNames[foundlock] + " UNCALIBRATED")
        elif (Response.get("state") == 254):
            Domoticz.Error("Nuki lock " + self.lockNames[foundlock] + " MOTOR BLOCKED")
        else:
            Domoticz.Log("Nuki lock temporary state ignored " + str(Response.get("stateName", "")))

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" +
                       str(Command) + "', Level: " + str(Level))

        # Locks: 1..N, Unlatch: N+1..2N
        if Unit > self.numLocks:
            idx = Unit - 1 - self.numLocks
            if idx < 0 or idx >= self.numLocks:
                Domoticz.Error("Invalid unlatch Unit: " + str(Unit))
                return
            lockid = str(self.lockIds[idx])
            lockname = self.lockNames[idx]
            action = 3  # unlatch
        else:
            idx = Unit - 1
            if idx < 0 or idx >= self.numLocks:
                Domoticz.Error("Invalid lock Unit: " + str(Unit))
                return
            lockid = str(self.lockIds[idx])
            lockname = self.lockNames[idx]

            if Command == 'On':
                action = 2
                sval = 'Locked'
                nval = 1
            else:
                action = 1
                sval = 'Unlocked'
                nval = 0

        Domoticz.Log("Switch device " + lockid + " with name " + lockname)
        req = ('http://' + str(self.bridgeIP) + ':' + self.bridgePort +
               '/lockAction?' + self.generateTokenString() +
               '&nukiId=' + lockid + '&action=' + str(action))
        Domoticz.Debug('Executing lockaction ' + str(req))

        try:
            resp_raw = urllib.request.urlopen(req).read()
        except HTTPError as e:
            Domoticz.Error('NUKI HTTPError code: ' + str(e.code))
        except URLError as e:
            Domoticz.Error('NUKI URLError Reason: ' + str(e.reason))
        else:
            strData = resp_raw.decode("utf-8", "ignore")
            Domoticz.Debug("Lock command response received " + strData)
            resp = json.loads(strData)
            if not resp.get("success", False):
                Domoticz.Error("Error switching lockstatus for lock " + lockname)
            else:
                # Only update main lock devices; unlatch is a pulse action
                if Unit <= self.numLocks:
                    UpdateDevice(Unit, nval, sval, 0)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called for connection '" + Connection.Name + "'.")
        if Connection.Name in self.httpServerConns:
            del self.httpServerConns[Connection.Name]

    def onHeartbeat(self):
        self.heartbeats += 1
        Domoticz.Debug("onHeartbeat called " + str(self.heartbeats))
        # heartbeat every 10 sec, pollInterval in minutes -> pollInterval*6 heartbeats
        if (self.heartbeats / 6) >= self.pollInterval:
            self.heartbeats = 0
            Domoticz.Log("onHeartbeat check locks")
            for i in range(self.numLocks):
                nukiId = self.lockIds[i]
                req = ('http://' + self.bridgeIP + ':' + self.bridgePort +
                       '/lockState?' + self.generateTokenString() +
                       '&nukiId=' + str(nukiId))
                Domoticz.Debug('Checking lockstatus ' + req)
                try:
                    resp_raw = urllib.request.urlopen(req).read()
                except HTTPError as e:
                    Domoticz.Error('NUKI HTTPError code: ' + str(e.code))
                except URLError as e:
                    Domoticz.Error('NUKI URLError Reason: ' + str(e.reason))
                else:
                    strData = resp_raw.decode("utf-8", "ignore")
                    Domoticz.Debug("Lock status received " + strData)
                    resp = json.loads(strData)

                    if resp.get("success", False):
                        batt = 10 if resp.get("batteryCritical", False) else 255
                        if resp.get("state") == 1:
                            UpdateDevice(i + 1, 1, "Locked", batt)
                        elif resp.get("state") == 3:
                            UpdateDevice(i + 1, 0, "Unlocked", batt)
                        elif resp.get("state") == 0:
                            Domoticz.Error("Nuki lock " + self.lockNames[i] + " UNCALIBRATED")
                        elif resp.get("state") == 254:
                            Domoticz.Error("Nuki lock " + self.lockNames[i] + " MOTOR BLOCKED")
                        else:
                            Domoticz.Log("Nuki lock temporary state ignored " + str(resp.get("stateName", "")))
                    else:
                        Domoticz.Log("Nuki lock false response received")


global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


def LogMessage(Message):
    mode = Parameters["Mode6"]
    if mode == "Debug":
        Domoticz.Debug(Message)
    elif mode == "File":
        try:
            with open("http.html", "w") as f:
                f.write(Message)
        except Exception:
            pass
    else:
        Domoticz.Log(Message)


def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return


def UpdateDevice(Unit, nValue, sValue, batt):
    Domoticz.Debug("UpdateDevice called with " + str(Unit) + ' ' + str(nValue) + ' ' + str(sValue) + ' ' + str(batt))
    if Unit in Devices:
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            if batt == 0:
                Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            else:
                Devices[Unit].Update(nValue=nValue, sValue=str(sValue), BatteryLevel=batt)
            Domoticz.Debug("Update " + str(nValue) + ":'" + str(sValue) + "' (" + Devices[Unit].Name + ")")
    return
