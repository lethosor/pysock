#!/usr/bin/env python

# Python 2 compatibility
from __future__ import print_function
__metaclass__ = type

import errno
import socket
import struct
import sys
import threading

if sys.version[0] == '2':
    import Queue as queue
else:
    import queue

SOCKET_CLOSED = (errno.EBADF, errno.EPIPE, errno.ECONNRESET)
SOCKET_NO_DATA = (errno.EAGAIN, )

def encode_message(data):
    return zlib.compress(pickle.dumps(data, 2))  # Python 2/3-compatible

def decode_message(data):
    return pickle.loads(zlib.decompress(data))

class Protocol:
    def encode(self, data):
        raise NotImplementedError
    def decode(self, data):
        raise NotImplementedError

class EventHandler:
    def __init__(self):
        self.callbacks = {}

    def bind(self, event, handler):
        if not event in self.callbacks:
            self.callbacks[event] = []
        if handler not in self.callbacks[event]:
            self.callbacks[event].append(handler)

    def unbind(self, event, handler):
        if event not in self.callbacks:
            raise ValueError('Unrecognized event: %s' % event)
        if handler not in self.callbacks[event]:
            raise ValueError('Handler not bound to event')
        self.callbacks[event].remove(handler)

    def trigger(self, event, *data):
        if event not in self.callbacks:
            raise ValueError('Unrecognized event: %s' % event)
        for handler in self.callbacks[event]:
            handler(*data)

class SocketSendThread(threading.Thread):
    def __init__(self, socket, protocol):
        threading.Thread.__init__(self)
        self.socket = socket
        self.protocol = protocol
        self.send_queue = queue.Queue()

    def run(self):
        try:
            while True:
                msg = self.protocol.encode(self.send_queue.get())
                self.socket.send(struct.pack('<i', len(msg)))
                self.socket.send(msg)
        except socket.error as e:
            if e.errno in SOCKET_CLOSED:
                pass
            else:
                raise

    def send(self, msg):
        self.send_queue.put(msg)

class SocketRecvThread(threading.Thread):
    def __init__(self, socket, protocol):
        threading.Thread.__init__(self)
        self.socket = socket
        self.protocol = protocol
        self.events = EventHandler()

    def run(self):
        try:
            while True:
                packet_length = struct.unpack('<i', self.socket.recv(4))[0]
                packet_contents = self.socket.recv(packet_length)
                self.events.trigger('receive', self.protocol.decode(packet_contents))
        except socket.error as e:
            if e.errno in SOCKET_CLOSED:
                pass
            else:
                raise

class SocketConnection:
    def __init__(self, socket, protocol):
        self.send_thread = SocketSendThread(socket, protocol)
        self.recv_thread = SocketRecvThread(socket, protocol)

    def listen(self):
        self.send_thread.start()
        self.recv_thread.start()

class Server:
    def __init__(self, host, port):
        self.addr = (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, port))
        self.socket.listen(4)

