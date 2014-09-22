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
SOCKET_NOT_CONNECTED = (errno.ENOTCONN, errno.EBADF)

# unique
SHUTDOWN = object()

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
            self.callbacks[event] = []
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
                msg = self.send_queue.get()
                if msg == SHUTDOWN:
                    break
                msg = self.protocol.encode(msg)
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
                self.events.trigger('close')
            else:
                raise
        except struct.error:
            # Fewer than 4 bytes received, connection closed
            self.events.trigger('close')

class SocketConnection:
    def __init__(self, socket, protocol):
        self.socket = socket
        self.send_thread = SocketSendThread(socket, protocol)
        self.recv_thread = SocketRecvThread(socket, protocol)

    def listen(self):
        self.send_thread.start()
        self.recv_thread.start()
        self.recv_thread.events.bind('close', lambda: self.close())

    def close(self):
        self.send_thread.send(SHUTDOWN)
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        except socket.error as e:
            if e.errno in SOCKET_NOT_CONNECTED:
                pass
            else:
                raise

class Server:
    def __init__(self, host, port):
        self.addr = (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, port))
        self.socket.listen(4)

