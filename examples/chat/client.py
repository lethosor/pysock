from __future__ import print_function
import pysock, proto, sys
if sys.version[0] == '3':
    import tkinter as tk
else:
    import Tkinter as tk

ADDRESS = ('localhost', 8100)
if len(sys.argv) >= 3:
    ADDRESS = (sys.argv[1], int(sys.argv[2]))

class Ui(tk.Frame):
    def __init__(self, parent):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.client = None
        self.grid()
        self.history = tk.Text(self, width=80, height=20, wrap=tk.WORD)
        self.history.grid(row=1, column=1, columnspan=3)
        self.history.config(state=tk.DISABLED)
        self.entry = tk.Text(self, width=80, height=2, wrap=tk.WORD)
        self.entry.grid(row=2, column=1, columnspan=3)
        self.entry.bind('<Return>', lambda event: [self.send(), 'break'][1])
        self.entry.focus_set()
        self.update()

    def parse_command(self, cmd):
        if not cmd.startswith('/'):
            return None
        return cmd[1:].split(' ')

    def connect(self):
        if self.client is not None and self.client.connected:
            self.log('[local] Already connected')
            return
        self.log('[local] Attempting to connect to server...')
        try:
            client = Client(ADDRESS[0], ADDRESS[1])
        except pysock.socket.error as e:
            self.log('[local] Could not connect to server. Type "/connect" to retry.')
            return
        self.client = client

    def disconnect(self):
        if self.client is not None:
            self.client.disconnect()

    def clear_entry(self):
        self.entry.delete(0.0, tk.END)

    def send(self):
        msg = self.entry.get(0.0, tk.END).rstrip('\n')
        cmd = self.parse_command(msg)
        if cmd:
            self.clear_entry()
            if cmd[0] == 'quit':
                self.disconnect()
                return
            elif cmd[0] == 'connect':
                self.connect()
                return
            elif cmd[0]:
                msg = {'command': True, cmd[0]: ' '.join(cmd[1:])}
        if self.client is None or not self.client.connected:
            return
        self.client.send(msg)
        self.clear_entry()

    def receive(self, msg):
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, '%s\n' % msg)
        self.history.see(tk.END)
        self.history.config(state=tk.DISABLED)
    log = receive

    def update(self):
        if self.client is not None:
            for msg in self.client.queue:
                if msg is Client.DISCONNECTED:
                    self.log('[local] Disconnected')
                else:
                    self.receive(msg)
            self.client.queue = []
        self.after(1, self.update)

class Client(pysock.Client):
    DISCONNECTED = object()
    protocol = proto.PickleProtocol()
    def on_connect(self):
        self.queue = []
    def on_receive(self, msg):
        self.queue.append(msg)
    def on_disconnect(self):
        self.queue.append(self.DISCONNECTED)

def main():
    root = tk.Tk()
    ui = Ui(root)
    ui.connect()
    try:
        root.mainloop()
    finally:
        if ui.client is not None:
            ui.client.disconnect()

if __name__ == '__main__':
    main()
