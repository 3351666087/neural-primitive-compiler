"""Client for the B2 pilot's ALFWorld server: one action per call, prints one text observation.

  python3 alf_client.py SOCKET reset
  python3 alf_client.py SOCKET act "go to fridge 1"
  python3 alf_client.py SOCKET done
"""

import json
import socket
import sys

sock, cmd = sys.argv[1], sys.argv[2]
arg = sys.argv[3] if len(sys.argv) > 3 else ""
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sock)
s.sendall((json.dumps({"cmd": cmd, "arg": arg}) + "\n").encode())
print(json.loads(s.makefile().readline())["obs"])
