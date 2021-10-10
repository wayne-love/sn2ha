import socket
import time
import traceback
import logging

socket.setdefaulttimeout(2)
logger = logging.getLogger(__name__)


class connection:

    _socket = None
    
    def _open_socket(self):

        _retries = 10
        _interval = 1
        _connected = False

        while not(_connected):
            logger.debug("Connecting to socket")
            try:
                self._socket = socket.socket()
                self._socket.connect(('WiFly-EZX', 2000))
                logger.info("Socket connected")
                return True
            except:
                logger.exception()
                self._socket.close()
                self._socket = socket.socket()
            logger.debug("Unable to connect to socket, retrying")
            time.sleep(_interval)
        
    def _send(self, s):
        self._socket.sendall(s.encode())
        time.sleep(0.25)

    def _read(self):
        return self._socket.recv(4096)

    def close(self):
        logger.debug("Closing socket")
        self._socket.close()

    def connect(self):
        _hello = "*HELLO*"
        _connected = False
        _interval = 1

        logger.debug("Starting connection handshake")

        while not(_connected):
            try:
                if self._open_socket():
                    hello = self._read().decode()
                    if hello == _hello:
                        return True
            except:
                self.close()
                logger.warning("No hello message received, retrying")
            time.sleep(_interval)
        


    def write(self,command,response,boolean_response):
        
        _retries = 3
        _interval = 1
        _connection_attempts = 0

        while _connection_attempts < 2:
            _connection_attempts = _connection_attempts + 1

            for count in range(_retries):
                result = ""
                try:
                    logger.debug("Sending %s",command)
                    self._send('\n')
                    self._send(command + "\n")
                    result = self._read().decode()
                    logger.debug("Response - %s",result)

                except ConnectionAbortedError:
                    logger.warning("Connection closed, reconnecting")
                    self.close()
                    self.connect()
                except:
                    logger.exception("Error writing to WiFly")

                if result != "":
                    if boolean_response:
                        if response == result[:len(response)]:
                            return True
                        else:
                            return False
                    else:
                        return result
                logger.warning("No response received to command, retrying")
                time.sleep(_interval)
            
            logger.warning("Unable to get response to comment, reconnecting")
            self.close()
            self.connect()


        return ""
