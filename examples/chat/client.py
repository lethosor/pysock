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
    def __init__(self, parent, client):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.client = client
        self.grid()
        self.history = tk.Text(self, width=80, height=20, wrap=tk.WORD)
        self.history.grid(row=1, column=1, columnspan=3)
        self.history.config(state=tk.DISABLED)
        self.entry = tk.Text(self, width=80, height=2, wrap=tk.WORD)
        self.entry.grid(row=2, column=1, columnspan=3)
        self.entry.bind('<Return>', lambda event: [self.send(), 'break'][1])
        self.entry.focus_set()
        self.update()

    def send(self):
        if not self.client.connected:
            return
        msg = self.entry.get(0.0, tk.END).rstrip('\n')
        self.entry.delete(0.0, tk.END)
        if msg == '/quit':
            self.client.disconnect()
            return
        self.client.send(msg)

    def receive(self, msg):
        self.history.config(state=tk.NORMAL)
        self.history.insert(tk.END, '%s\n' % msg)
        self.history.see(tk.END)
        self.history.config(state=tk.DISABLED)

    def update(self):
        for msg in self.client.queue:
            self.receive(msg)
        self.client.queue = []
        if not self.client.connected:
            self.receive('<Disconnected>')
            return
        self.after(1, self.update)

class Client(pysock.Client):
    protocol = proto.PickleProtocol()
    def on_connect(self):
        print('- connected')
        self.queue = []
    def on_receive(self, msg):
        self.queue.append(msg)
    def on_disconnect(self):
        print('- disconnected')

def main():
    print('Attempting to connect to server...')
    try:
        client = Client(ADDRESS[0], ADDRESS[1], retry_timeout=10)
    except pysock.socket.error as e:
        print('Could not connect to server.')
        return
    root = tk.Tk()
    Ui(root, client)
    try:
        root.mainloop()
    finally:
        client.disconnect()

if __name__ == '__main__':
    main()
