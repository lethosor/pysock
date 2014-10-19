#!/usr/bin/env python

# Python 2 compatibility
from __future__ import print_function
__metaclass__ = type

import errno
import socket
import struct
import sys
import threading
import time

if sys.version[0] == '2':
    import Queue as queue
else:
    import queue

SOCKET_CLOSED = (errno.EBADF, errno.EPIPE, errno.ECONNRESET)
SOCKET_NO_DATA = (errno.EAGAIN, )
SOCKET_NOT_CONNECTED = (errno.ENOTCONN, errno.EBADF)

# unique
SHUTDOWN = object()

class Protocol:
    def encode(self, data):
        raise NotImplementedError
    def decode(self, data):
        raise NotImplementedError

class EventHandler:
    def __init__(self):
        self.callbacks = {}
        self.handlers = []
        self.lock = threading.RLock()

    def bind(self, event, callback):
        with self.lock:
            if not event in self.callbacks:
                self.callbacks[event] = []
            if callback not in self.callbacks[event]:
                self.callbacks[event].append(callback)

    def add_handler(self, obj):
        """ Bind all events to a corresponding 'on_event' method of obj, if available """
        with self.lock:
            self.handlers.append(obj)

    def unbind(self, event, callback):
        with self.lock:
            if event not in self.callbacks:
                raise ValueError('Unrecognized event: %s' % event)
            if callback not in self.callbacks[event]:
                raise ValueError('Handler not bound to event')
            self.callbacks[event].remove(callback)

    def remove_handler(self, obj):
        with self.lock:
            if obj not in self.handlers:
                raise ValueError('Handler not registered')
            self.handlers.remove(obj)

    def trigger(self, event, *args, **kwargs):
        with self.lock:
            if event not in self.callbacks:
                self.callbacks[event] = []
            for callback in self.callbacks[event]:
                callback(*args, **kwargs)
            for obj in self.handlers:
                if hasattr(obj, 'on_' + event):
                    callback = getattr(obj, 'on_' + event)
                    if hasattr(callback, '__call__'):
                        callback(*args, **kwargs)

class SocketSendThread(threading.Thread):
    def __init__(self, socket, protocol):
        super(SocketSendThread, self).__init__()
        self.socket = socket
        self.protocol = protocol
        self.events = EventHandler()
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
        finally:
            self.events.trigger('close')

    def send(self, msg):
        self.send_queue.put(msg)

class SocketRecvThread(threading.Thread):
    def __init__(self, socket, protocol):
        super(SocketRecvThread, self).__init__()
        self.socket = socket
        self.protocol = protocol
        self.events = EventHandler()

    def run(self):
        try:
            while True:
                packet_length = self.socket.recv(4)
                if len(packet_length) != 4:
                    break
                packet_length = struct.unpack('<i', packet_length)[0]
                packet_contents = self.socket.recv(packet_length)
                self.events.trigger('receive', self.protocol.decode(packet_contents))
        except socket.error as e:
            if e.errno in SOCKET_CLOSED:
                self.events.trigger('close')
            else:
                raise
        except struct.error:
            # Fewer than 4 bytes received, connection closed
            pass
        finally:
            self.events.trigger('close')

class SocketConnection:
    def __init__(self, socket, protocol):
        self.connected = False
        self.socket = socket
        self.events = EventHandler()
        self.send_thread = SocketSendThread(socket, protocol)
        self.recv_thread = SocketRecvThread(socket, protocol)
        self.recv_thread.events.bind('close', lambda: self.close())

    def listen(self):
        self.send_thread.start()
        self.recv_thread.start()
        self.connected = True

    def send(self, msg):
        self.send_thread.send(msg)

    def close(self):
        if not self.connected:
            return
        self.connected = False
        self.send_thread.send(SHUTDOWN)
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
        except socket.error as e:
            if e.errno in SOCKET_NOT_CONNECTED:
                pass
            else:
                raise
        finally:
            self.events.trigger('close')

class Server:
    def __init__(self, host, port, protocol=None, reuse_addr=False):
        self.addr = (host, port)
        self.protocol = protocol or self.protocol
        if not self.protocol:
            raise ValueError('Undefined protocol')
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if reuse_addr:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(4)

class Client:
    """ A client that connects to a Server instance """
    def __init__(self, host, port, protocol=None,
                 retry_timeout=0, retry_delay=0.1):
        """ Connect to a server

        host: Destination hostname (e.g. 'localhost')
        port: Destination port (e.g. 8000)
        protocol: A Protocol instance to use to communicate with the server.
            This does not necessarily have to be the same type as the protocol
            used on the server. Can also be specified as a class attribute:

            class ExampleClient(pysock.Client):
                protocol = ExampleProtocol()
                # ...

        retry_timeout: The maximum time (in seconds) that can pass before a
            connection is considered unsuccessful. Note that this timeout is
            only triggered when a connection attempt fails (for example,
            a slow connection will not trigger the timeout). A value of 0 will
            allow exactly one connection attempt.
        retry_delay: The time to wait after a connection attempt fails before
            retrying. Setting this below 0.1 is not recommended, as connection
            attempts that fail immediately will result in excessive attempts.
            retry_timeout is checked after this delay has elapsed.
        """

        self.events = EventHandler()
        self.connected = False
        self.addr = (host, port)
        self.protocol = protocol or self.protocol
        if not self.protocol:
            raise ValueError('Undefined protocol')

        # Attempt to connect to server
        initial_time = time.time()
        while True:
            try:
                # Initialize raw socket
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect(self.addr)
            except socket.error as e:
                time.sleep(retry_delay)
                if time.time() - initial_time >= retry_timeout:
                    raise
            else:
                # Connection successful
                break
        self.connection = SocketConnection(self.socket, self.protocol)

        # Set up event handlers
        self.events.add_handler(self)
        self.connection.recv_thread.events.bind('receive', lambda msg:
            self.events.trigger('receive', msg))
        self.connection.events.bind('close', lambda:
            self.events.trigger('disconnect'))
        self.events.bind('disconnect', self.disconnect)

        # Connect!
        self.connection.listen()
        self.connected = True
        self.events.trigger('connect')

    def send(self, msg):
        self.connection.send(msg)
        self.events.trigger('send', msg)

    def disconnect(self):
        self.connection.close()
        self.connected = False

    def on_connect(self): pass
    def on_send(self, msg): pass
    def on_receive(self, msg): pass
    def on_disconnect(self): pass

