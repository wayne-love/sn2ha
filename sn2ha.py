import socket               
import time
import paho.mqtt.client as mqtt
import logging
import json
import configparser
import io
from datetime import timedelta,datetime
from MQTTHandler import MQTTHandler
from connection import connection
import connection


# Define constants
HPUMP_MODES = {
    0: "auto",
    1: "heat",
    2: "cool",
    3: "off"
}



logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


# Load the configuration file
try:
    config = configparser.ConfigParser()
    config.read('sn2ha.ini')
except:
    logger.exception("Unable to parse config file.")
    quit(-1)
    
# Set environment
spaName = config.get("sn2ha","spaName")
homeAssistantDiscovery = config.get("sn2ha","homeAssistantDiscovery")
mqttServer = config.get("sn2ha","mqttServer")
baseTopic = config.get("sn2ha","baseTopic") + spaName


mqttHandler = MQTTHandler(mqttServer, baseTopic + "/debug")
mqttHandler.setLevel(logging.DEBUG)
mqttHandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))
logger.addHandler(mqttHandler)

c = connection.connection()



class SpaNetSpa:
    set_temp = 0
    current_temp = 0
    heating = False
    cleaning_UV = False
    cleaning_Sanitise = False
    lights = False
    hpump_ambi_temp = 0
    hpump_cond_temp = 0
    hpump_mode_num = 0
    hpump_mode_txt = ""
    element_boost = False
    _response = b''


    def send(self, s, message):
        s.send(message)
        time.sleep(0.25)

    def send_command(self, socket, command, result):
        try:
            logger.debug("Sent "+ command)
            command = command + '\n'
            self.send(socket,command.encode())
            recv_str = socket.recv(1024).decode().rstrip() #convert byte array to string then strip trailing CRLF
            if recv_str != result:
                logger.error("Unexpect result to spa request")
                return False
            return True
        except:
            logger.error("No response received to spa write")
            return False

        
    def sync_status(self):
  
        global commandBuffer

        logger.debug("Processsing "+str(len(commandBuffer))+" commands")
        newBuffer = dict(commandBuffer)
        commandBuffer = {}

        for entry in newBuffer:
            setValue = newBuffer[entry]
            if entry=="cleaning_Sanitise":
                c.write("W12","W12",True)
            if entry=="lights":
                c.write("W14","W14",True)
            if entry=="set_temp":
                tempStr = str(int(float(setValue)*10))
                c.write("W40:"+tempStr,tempStr,True)
            if entry=="hpump_mode_txt":
                for key,value in HPUMP_MODES.items():
                    if value==setValue:
                        c.write("W99:"+str(key),str(key),True)
            if entry=="element_boost":
                if setValue=="ON":
                    c.write("W98:1","1",True)
                else:
                    c.write("W98:0","0",True)

        logger.debug("Requesting status")

        response_str = c.write("RF","RF",False)
        logger.debug("Response - " + response_str)
        if response_str != "":
        
            response = response_str.split(",")
            
            if response!="":
                self.set_temp = int(response[128])/10
                self.current_temp = int(response[107])/10
                self.lights = bool(int(response[106])) # Lights on or off
                self.heating = bool(int(response[104])) # Is the heating running
                self.cleaning_UV = bool(int(response[103])) # Is the ozone/UV cleaning running
                self.cleaning_Sanitise = bool(int(response[108])) # Is the sanatise cycle running
                self.hpump_ambi_temp = int(response[251]) # heat pump ambient temp
                self.hpump_cond_temp = int(response[252]) # heat pump condensor temp
                self.hpump_mode_num = int(response[176]) # heat pump mode (numeric)
                self.element_boost = bool(int(response[175])) #element boost
                self.hpump_mode_txt = HPUMP_MODES[self.hpump_mode_num] #heat pump mode (string)
                return True
            else:
                logger.error("Error reading from SpaNet controller")
                return False
        else:
            logger.warning("No response received, resetting connection")
            c.close()
            c.connect()

def on_message(client, userdata, message):
    topic = str(message.topic).split("/")[2]
    payload = str(message.payload.decode("utf-8"))
    logger.debug("message received "+topic+","+payload)
    commandBuffer.update({topic: payload})

logger.info("Start")

commandBuffer = {}



client = mqtt.Client()
client.will_set(baseTopic + "/available","offline", 0, True)

try:
    client.connect(mqttServer)
except:
    logger.exception("Unable to connect to MQTT server")
    quit(-1)

client.loop_start()

client.publish(baseTopic + "/available","online", 0, True)

client.on_message = on_message
client.subscribe(baseTopic + "/+/set")

if homeAssistantDiscovery:

    # Temperature current & set
    ha_discovery = {
        "name": spaName,
        "max_temp": 41.0,
        "min_temp": 5.0,
        "precision": 0.1,
        "temp_step": 0.5,
        "unique_id": "spanet_" + spaName +"_heating",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "availability_topic": baseTopic+"/available",
        "temperature_state_topic": baseTopic+"/set_temp/value",
        "current_temperature_topic": baseTopic+"/current_temp/value",
        "temperature_command_topic": baseTopic+"/set_temp/set",
        "modes": ["off","cool","heat","auto"],
        "mode_state_topic": baseTopic + "/hpump_mode_txt/value",
        "mode_command_topic": baseTopic + "/hpump_mode_txt/set",
        "aux_state_topic": baseTopic + "/element_boost/value",
        "aux_command_topic": baseTopic + "/element_boost/set"
    }
    client.publish("homeassistant/climate/spanet_"+spaName+"/config",json.dumps(ha_discovery),retain=True)

    #Heat pump ambient temp
    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "device_class": "temperature",
        "state_topic":baseTopic+"/hpump_ambi_temp/value",
        "name": "Heat pump ambient temperature",
        "unique_id": "spanet_" + spaName +"_hpump_ampi_temp",
        "unit_of_measurement": "\u00B0C"
    }
    client.publish("homeassistant/sensor/spanet_"+spaName+"/hpump_ambi_temp/config",json.dumps(ha_discovery),retain=True)

    #Heat condensor temp
    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "device_class": "temperature",
        "state_topic":baseTopic+"/hpump_cond_temp/value",
        "name": "Heat pump condensor temperature",
        "unique_id": "spanet_" + spaName +"_hpump_cond_temp",
        "unit_of_measurement": "\u00B0C"
    }
    client.publish("homeassistant/sensor/spanet_"+spaName+"/hpump_cond_temp/config",json.dumps(ha_discovery),retain=True)


    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "device_class": "heat",
        "state_topic":baseTopic+"/heating/value",
        "name": "Heating",
        "unique_id": "spanet_" + spaName +"_heating",
        "payload_on":"True",
        "payload_off":"False"
    }

    client.publish("homeassistant/binary_sensor/spanet_"+spaName+"/heating/config",json.dumps(ha_discovery),retain=True)

    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "state_topic":baseTopic+"/cleaning_UV/value",
        "name": "UV/Ozone Cleaning",
        "unique_id": "spanet_" + spaName +"_cleaning_UV",
        "payload_on":"True",
        "payload_off":"False"
    }

    client.publish("homeassistant/binary_sensor/spanet_"+spaName+"/cleaning_UV/config",json.dumps(ha_discovery),retain=True)

    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "state_topic":baseTopic+"/cleaning_Sanitise/value",
        "command_topic":baseTopic+"/cleaning_Sanitise/set",
        "name": "Sanitise Cycle",
        "unique_id": "spanet_" + spaName +"_cleaning_Sanitise",
        "payload_on":"True",
        "payload_off":"False"
    }

    client.publish("homeassistant/switch/spanet_"+spaName+"/cleaning_Sanitise/config",json.dumps(ha_discovery),retain=True)

    ha_discovery = {
        "availability_topic": baseTopic+"/available",
        "device": {
            "identifiers": [spaName],
            "manufacturer": "SpaNet",
            "name": spaName
        },
        "state_topic":baseTopic+"/lights/value",
        "command_topic":baseTopic+"/lights/set",
        "name": "Lights",
        "unique_id": "spanet_" + spaName +"_lights",
        "payload_on":"True",
        "payload_off":"False"
    }

    client.publish("homeassistant/light/spanet_"+spaName+"/lights/config",json.dumps(ha_discovery),retain=True)




c.connect()
spa = SpaNetSpa()

lastUpdate = datetime.now() - timedelta(seconds=300) # set the lastupdate to be 5 minutes ago to force the first read.

while True:
    # Loop once per second and check if there are any commands
    # that need to be sent to the spa.  If so then send immediately.
    # If not then keep looping until 65 seconds have passed then 
    # poll spa for updated status.  Using 65 as there seems to be some 
    # sort of 60 second process on the WiFly that we can get caught up with that 
    # causes the script to fail to read.
    timeSinceUpdate = datetime.now() - lastUpdate
    if (timeSinceUpdate.total_seconds()/65 > 1) or (len(commandBuffer)>0): 
        if spa.sync_status():
            logger.info("Successful read")
            lastUpdate = datetime.now()
            client.publish(baseTopic + "/set_temp/value",spa.set_temp,retain=True)
            client.publish(baseTopic + "/hpump_ambi_temp/value",spa.hpump_ambi_temp,retain=True)
            client.publish(baseTopic + "/hpump_cond_temp/value",spa.hpump_cond_temp,retain=True)
            client.publish(baseTopic + "/current_temp/value",spa.current_temp,retain=True)
            client.publish(baseTopic + "/heating/value",spa.heating,retain=True)
            client.publish(baseTopic + "/cleaning_UV/value",spa.cleaning_UV,retain=True)
            client.publish(baseTopic + "/cleaning_Sanitise/value",spa.cleaning_Sanitise,retain=True)
            client.publish(baseTopic + "/lights/value",spa.lights,0,True)
            client.publish(baseTopic + "/hpump_mode_num/value",spa.hpump_mode_num,0,True)
            client.publish(baseTopic + "/hpump_mode_txt/value",spa.hpump_mode_txt,0,True)
            client.publish(baseTopic + "/element_boost/value","ON" if spa.element_boost else "OFF",0,True)

    time.sleep(1)
