import socket               
import time

socket.setdefaulttimeout(5)
s = socket.socket()        

s.connect(('WiFly-EZX', 2000))
print (s.recv(1024))
time.sleep(0.5)
s.send('\n'.encode())
time.sleep(0.5)
s.send('RF\n'.encode())
response = s.recv(1024).split(b",")

x = 0
for value in response:
    print(x,value)
    x = x + 1

s.close                     # Close the socket when done