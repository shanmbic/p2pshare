'Author : Shantanu Srivastava'

import socket
import fcntl
import struct
import threading
import os
import ast
import time
from Tkinter import Tk, BOTH, Listbox, StringVar, END, Label, Entry
from ttk import Frame, Button, Style
import tkFileDialog 
import tkMessageBox
import pickle
import sys
import Queue


def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


class Peer(Frame):

    def __init__(self, parent, ip='0.0.0.0', port=5228):
        #self._nick = nick
        Frame.__init__(self, parent) 
        self._addr = get_ip_address('eth0')
        self._port = port
        self._connection_ports = [5229,5230,5231,5232,5233,5234,5235]
        self._peers = []
        self._peers_joined = {}
        self._clients_running ={}
        self._pid = (self._addr , self._port)
        self._buf = 1024
        self._files = []
        self._socket = self.start_server(self._pid)
        self._running = False
        self._threads = []
        self.parent = parent
        self.download_dir = '/'
        self.showfiles = []
        self.initUI()
        self.run()


    def get_pid(self):
        return self._pid

    def start_server(self, pid):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(pid)
            sock.settimeout(30)
        except:
            sock=None
        #print "Server started at %s and %s" % pid
        return sock

    def start_pinging(self):
        while self._running:
            time.sleep(3)
            for peers in self._peers_joined.keys():
                conn = self._peers_joined[peers]
                try:
                    data={'type':"Ping"}
                    conn.send(str(data))
                except:
                    pass


    def quit(self):
        quit_flag = False
        for peer in self._peers_joined.keys():
            conn = self._peers_joined[peer]
            data = {'type' : 'Quit'}
            try:
                conn.send(str(data))
                conn.shutdown(2)
                conn.close()
            except:
                pass
        for peer in self._clients_running.keys():
            self._clients_running[peer] = False
        self._running=False
        sock = socket.socket(socket.AF_INET, 
                  socket.SOCK_STREAM)
        i=50000
        while not quit_flag:
            try:
                sock.bind((self._addr, i))
                quit_flag=True
            except:
                i+=1
        sock.connect((self._addr, self._port))
        sock.shutdown(2)
        sock.close()


    def get_peers(self):
        s=''
        for peer in self._peers_joined.keys():
            s+=str(peer[0]) + ':' + str(peer[1])
            s+=','
        return s

    def update_peers(self):
        for peer in self._peers_joined.keys():
            conn = self._peers_joined[peer]
            data = {}
            data['type'] = 'Update'
            data['payload'] = self.get_peers()
            conn.send(str(data).encode())
            time.sleep(5)
            data = {'type':'Filelist', 'payload':'|'.join(self._files)}
            conn.send(str(data).encode())

    def update_filelist(self):
        try:
            with open('filelist', 'r') as f:
                self._files = list(set(pickle.load(f)))
            for x in self._files:
                s=x.replace(os.path.dirname(x), '')
                s=s.replace("/","")
                self.lbfiles.insert(END, s)
                if s not in self.showfiles:
                    self.showfiles.append(s)
            self.lbfiles.update_idletasks()
        except:
            pass

    def read_showfiles(self):
        self.lbfiles.delete(0, END)
        for files in self.showfiles:
            self.lbfiles.insert(END,files)
        self.lbfiles.update_idletasks()
        self.parent.after(1000, self.read_showfiles)
        

    def add_peers(self, peers):
        peers = peers.split(",")
        for peer in peers:
            if peer != '':
                addr , port = peer.split(':')
                if (addr, int(port)) in self._peers:
                    pass
                else:
                    self._peers.append((addr, int(port)))

    def query_file(self):
        filename=str(self.fileSearchEntry.get())
        for peer in self._peers_joined.keys():
            conn = self._peers_joined[peer]
            data = {}
            data['type'] = 'Query'
            data['payload'] = filename
            data['ttl'] = 10
            conn.send(str(data))

    def connect(self):
        ip=str(self.addr_ip_entry.get())
        port=int(self.addr_port_entry.get())
        nick=str(self.addr_nick_entry.get())
        socket_found_flag=False
        if not (ip, port) in self._peers_joined.keys():
            while not socket_found_flag:
                sock_port = self._connection_ports.pop(0)
                conn_sock = self.start_server((self._addr, sock_port))
                if conn_sock != None:
                    socket_found_flag=True
            conn_sock.connect((ip, port))
            msg=conn_sock.recv(self._buf)
            conn_sock.shutdown(2)
            conn_sock.close()
            msg=ast.literal_eval(msg)
            if msg['type']=='Connect':
                conn_sock = self.start_server((self._addr, sock_port))
                addr = msg['payload'].split(":")
                conn_sock.connect((addr[0], int(addr[1])))
                self._peers_joined[(addr[0], addr[1] )]=conn_sock
                self.lbpeers.insert(END, nick+'@'+str(addr[0])+':'+str(addr[1]))
                self.lbpeers.update_idletasks()
                client_thread = threading.Thread(name='Client Thread'+str(addr), target=self.handle_client_connection, args=(conn_sock, (addr[0], int(addr[1]))))
                self._threads.append(client_thread)
                client_thread.start()
            #self.run()
        else:
            print "Already connected"

    def process_query(self, filename, ttl):
        resp = {}
        found_flag = False
        if ttl == 0 :
            resp['result'] = False
            resp['resource_name'] = filename
            resp['size'] = 0
            resp['ttl'] = ttl - 1
            return resp 
        for file_name in self._files:
            if file_name.find(filename)!=-1:
                resp['result'] = True
                resp['resource_name'] = file_name
                resp['size'] = os.path.getsize(file_name)
                found_flag = True
                resp['ttl'] = ttl - 1
                return resp
        resp['result'] = False
        resp['resource_name'] = filename
        resp['size'] = 0
        resp['ttl'] = ttl - 1
        return resp

    def send_file(self, filename, client_conn):
        with open(filename, 'rb') as f:
            chunk = f.read(1024)
            while chunk:
                client_conn.send(chunk)
                chunk = f.read(1024)
            print "File sent"

    def handle_client_connection(self, client_conn, client_pid):
        self._clients_running[client_pid] = True
        print threading.currentThread().getName() , 'Started'
        while self._running and self._clients_running[client_pid]:
            data=''
            while len(data) == 0 and self._clients_running[client_pid]:
                try:
                    data = client_conn.recv(self._buf)
                except:
                    self.statusLabel.config(text="Connection closed by %s" % client_pid)
            print data
            try:
                data=ast.literal_eval(data)
            except:
                data={'type':'corrupt'}
            if data['type'] == 'Update':
                self.statusLabel.config(text="Peer list recieved from %s and %s" % client_pid)
                print data['payload']
                self.add_peers(data['payload'])

            elif data['type'] == 'Filelist':
                for files in data['payload'].split('|'):
                    s=files.replace(os.path.dirname(files), '')
                    s=s.replace("/","")
                    if s not in self.showfiles:
                        self.showfiles.append(s)

            elif data['type'] == 'List':
                payload = self.get_peers()
                data = { 'type' : 'ListREPL', 'payload' : payload}
                client_conn.send(data.encode())

            elif data['type'] == 'ListREPL':
                self.add_peers(data['payload'])

            elif data['type'] == 'Query':
                resp = self.process_query(data['payload'], data['ttl'])
                if resp['result'] == True:
                    payload = resp
                    data = { 'type' : 'QueryREPL', 'payload': payload}
                    client_conn.send(str(data))
                if resp['result'] == False:
                    payload = resp
                    data = { 'type' : 'QueryREPL', 'payload': payload}
                    client_conn.send(str(data))

            elif data['type'] == 'QueryREPL':
                if not data['payload'] == None and data['payload']['result'] == True :
                    data = { 'type':'Fget', 'resource_name': data['payload']['resource_name']}
                    client_conn.send(str(data))

            elif data['type'] == 'Fget':
                data['type'] = 'FgetREPL'
                s=data['resource_name'].replace(os.path.dirname(data['resource_name']), '')
                s=s.replace("/","")
                x=data['resource_name']
                data['resource_name'] = s
                data['size'] = os.path.getsize(x)
                client_conn.send(str(data))
                self.send_file(x, client_conn)

            elif data['type'] == 'FgetREPL':
                with open(self.download_dir + '/' + data['resource_name'], 'w') as f:
                    size=data['size']
                    chunk = 'NonNone'
                    q, rem = divmod(size, self._buf)
                    i=1
                    while chunk and i <= q:
                        chunk = client_conn.recv(self._buf) 
                        f.write(chunk)
                        i+=1
                    chunk = client_conn.recv(rem)
                    f.write(chunk)
                    self.statusLabel.config(text="File download completed %s" % (data['resource_name'],))
                    self._files.append(self.download_dir + '/' + data['resource_name'])

            elif data['type'] == 'Quit':
                print "Client %s quitting" % (client_pid,)
                self._clients_running[client_pid]=False

        self.statusLabel.config( text="%s Exiting" % (threading.currentThread().getName(),))

    def add_files(self, filename):
        if os.path.isfile(filename):
            self._files.append(filename)
            print "File added %s" % (filename,)
            s=filename.replace(os.path.dirname(filename), '')
            self.lbfiles.insert(END, s)
            self.lbfiles.update_idletasks()
        elif not os.path.isfile(filename):
            filename = str(os.cwd()) + filename
            if os.path.isfile(filename):
                self._files.append(filename)
                print "File added %s" % (filename,)
                self.lbfiles.insert(END, filename)
                self.lbfiles.update_idletasks()
            else:
                print "File does not exist"

    def start_listening(self, conn_sock):
        flag=False
        connec , addr = None, None
        while not flag:
            conn_sock.listen(0)
            connec, addr = conn_sock.accept()
            if not addr in self._peers_joined:
                self._peers_joined[addr]=connec
            print self._peers_joined
            self.lbpeers.insert(END, addr)
            self.lbpeers.update_idletasks()
            self.statusLabel.config( text="Connected to %s and %s" % addr)
            self.update_peers()
            flag=True
        return (connec, addr)
    
    def listen_peers(self):
        self._socket.settimeout(None)
        while self._running:
            try:
                connection, addr=self._socket.accept()
            except:
                pass
            if (int(addr[1]) /10)%5000==0:
                break
            else:
                self.statusLabel.config(text="connection recieved from %s and %s" % addr)
                if len(self._connection_ports) != 0:
                    socket_found_flag=False
                    while not socket_found_flag:
                        port=int(self._connection_ports.pop(0))
                        conn_sock = self.start_server((self._addr, port))
                        if conn_sock != None:
                            socket_found_flag=True
                    msg={'type':'Connect', 'payload':str(self._addr)+':'+str(port)}
                    connection.send(str(msg))
                    connection.shutdown(2)
                    connection.close()
                    self.statusLabel.config(text="Started listening on port %s" % (port,))
                    resp = self.start_listening(conn_sock)
                    client_thread = threading.Thread(name='Client Thread'+str(addr), target=self.handle_client_connection, args=(resp[0], resp[1]))
                    self._threads.append(client_thread)
                    client_thread.start()
                #thread.start_new_thread(self.handle_client_connection, (resp[0], resp[1]))
        self._socket.shutdown(2)
        self._socket.close()
        with open('filelist','wb') as f:
            pickle.dump(self._files, f)
        self.statusLabel.config(text='Server shutting down')

    def run(self):
        if self._running == False :
            self._running = True 
        self.statusLabel.config(text="Server started , Waiting for peers")
        self._socket.listen(5)
        listen_thread = threading.Thread(name='Main_listen_thread', target=self.listen_peers)
        self._threads.append(listen_thread)
        listen_thread.start()
        ping_thread = threading.Thread(name='Pinging thread', target=self.start_pinging)
        self._threads.append(ping_thread)
        ping_thread.start()
        self.update_filelist()
        #thread.start_new_thread(self.listen_peers,())


    def initUI(self):
        self.parent.title("P2P Client")
        self.style = Style()
        self.style.theme_use("default")

        self.pack(fill=BOTH, expand=1)

        quitButton = Button(self, text="Quit Server",
            command=self.quit)
        quitButton.place(x=540, y=247)

        labelPeers = Label(self.parent, text="Peers in Network")
        labelPeers.pack()
        labelPeers.place(x=20, y=10)


        self.lbpeers = Listbox(self)   
        self.lbpeers.place(x=20, y=30)


        labelFiles = Label(self.parent, text="Files")
        labelFiles.pack()
        labelFiles.place(x=205, y=10)

        self.lbfiles = Listbox(self)    
        self.lbfiles.place(x=205, y=30)


        labelMessages = Label(self.parent, text="Messages")
        labelMessages.pack()
        labelMessages.place(x=410, y=10)

        self.connectPeerLabel = Label(self.parent, text='Connect to a peer on the P2P Network')
        self.connectPeerLabel.pack()
        self.connectPeerLabel.place(x=395, y=10)
        self.addr_ip_entry = Entry(self.parent, bd=2)
        self.addr_ip_entry_Label = Label(self.parent, text='Enter IP')
        self.addr_port_entry = Entry(self.parent, bd=2)
        self.addr_port_entry_Label = Label(self.parent, text='Enter Port')
        self.addr_nick_entry = Entry(self.parent, bd=2)
        self.addr_nick_entry_Label = Label(self.parent, text='Enter Nick')
        self.addr_ip_entry.pack()
        self.addr_ip_entry_Label.pack()
        self.addr_nick_entry.pack()
        self.addr_nick_entry_Label.pack()
        self.addr_port_entry.pack()
        self.addr_port_entry_Label.pack()
        self.addr_ip_entry_Label.place(x=395,y=30)
        self.addr_ip_entry.place(x=395, y=50)
        self.addr_port_entry_Label.place(x=395, y=75)
        self.addr_port_entry.place(x=395, y=95)
        self.addr_nick_entry_Label.place(x=395, y=120)
        self.addr_nick_entry.place(x=395,y=140)

        connectButton = Button(self, text="Connect Peer",
            command=self.connect)
        connectButton.place(x=395, y=170)

        self.fileSearchLabel = Label(self.parent, text='Enter File name to search')
        self.fileSearchEntry = Entry(self.parent, bd=2)
        self.fileSearchButton = Button(self, text="Search", command=self.query_file)
        self.fileSearchLabel.pack()
        self.fileSearchEntry.pack()
        self.fileSearchLabel.place(x=20, y=230)
        self.fileSearchEntry.place(x=20, y=250)
        self.fileSearchButton.place(x=205, y=247)

        fileOpenButton = Button(self, text="Add File", command=self.onOpen)
        fileOpenButton.place(x=205, y=200)

        serverInfoLabel = Label(self.parent, text='Server running at IP:%s , Port:%s' % (self._pid))
        serverInfoLabel.pack()
        serverInfoLabel.place(x=330, y=205)

        self.statusLabel = Label(self.parent)
        self.statusLabel.pack()
        self.statusLabel.place(x=10, y=300)

        dirselectButton = Button(self, text='Download location', command=self.setDir)
        dirselectButton.place(x=300, y=247)
        self.parent.after(1000, self.read_showfiles)


    def setDir(self):
        self.download_dir = tkFileDialog.askdirectory()
        self.statusLabel.config(text="Download directory set to:%s" % (self.download_dir,))

    def onOpen(self):
        ftypes = [('All files', '*')]
        dlg = tkFileDialog.Open(self, filetypes = ftypes)
        fl = dlg.show()
        self.add_files(fl)