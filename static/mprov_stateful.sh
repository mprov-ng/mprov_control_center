#!/bin/bash
which python3 
/usr/bin/python3 /tmp/mprov_stateful.py
/bin/setsid /bin/bash -m  <> /dev/tty1 >&0 2>&1