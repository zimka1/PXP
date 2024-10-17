import socket
import threading
import time


isPartnerHere = 0
heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = 0


def receive_handshake(addr):
    global isPartnerHere
    print("Received SYN")
    sock.sendto(b"SYN-ACK", addr)
    data, addr = sock.recvfrom(1024)
    if data == b"ACK":
        print("Handshake complete.")
        isPartnerHere = 1


def continue_handshake():
    global isPartnerHere
    print("Received SYN-ACK, sending ACK")
    sock.sendto(b"ACK", (remote_ip, remote_port))
    print("Handshake complete.")
    isPartnerHere = 1


def receive_termination(addr):
    global isPartnerHere
    print("Received FIN")
    # 2. Node 2: ACK → Node 1
    sock.sendto(b"FIN-ACK", addr)
    # 3. Node 2: FIN → Node 1
    sock.sendto(b"FIN-FIN", addr)
    data, addr = sock.recvfrom(1024)
    if data == b"ACK":
        isPartnerHere = 0
        print("Connection terminated.")


def continue_termination():
    global isPartnerHere
    print("Received ACK, waiting for FIN")
    data, addr = sock.recvfrom(1024)
    if data == b"FIN-FIN":
        print("Received FIN, sending final ACK")
        # 4. Node 1: ACK → Node 2
        sock.sendto(b"ACK", addr)
        print("Connection terminated.")
        isPartnerHere = 0


def wait_for_heartbeat():
    global isPartnerHere
    while True:
        if isPartnerHere:
            heartbeat_monitor()


def heartbeat_monitor():
    global heartbeat_missed, isPartnerHere, heartbeat_received
    while isPartnerHere:
        time.sleep(heartbeat_interval)

        sock.sendto(b"HEARTBEAT", (remote_ip, remote_port))

        time.sleep(heartbeat_interval_to_ans)

        if heartbeat_received:
            heartbeat_missed = 0
            print("All good!")
        else:
            heartbeat_missed += 1

        heartbeat_received = 0

        if heartbeat_missed >= max_missed_heartbeats:
            print("Connection lost. No response from the partner.")
            heartbeat_missed = 0
            isPartnerHere = 0
            break


def receive_message():
    global heartbeat_received

    while True:
        data, addr = sock.recvfrom(1024)

        # if someone want to reconnect
        if data == b"SYN":
            receive_handshake(addr)
            continue

        if data == b"SYN-ACK":
            continue_handshake()
            continue

        # if someone want to disconnect
        if data == b"FIN":
            receive_termination(addr)
            continue

        if data == b"FIN-ACK":
            continue_termination()
            continue

        if data == b"HEARTBEAT" and isPartnerHere == 1:
            print("Received HEARTBEAT")
            sock.sendto(b"HEARTBEAT-ACK", addr)
            continue
        elif data == b"HEARTBEAT":
            continue

        if data == b"HEARTBEAT-ACK" and isPartnerHere == 1:
            print("Received HEARTBEAT-ACK")
            heartbeat_received = 1
            continue
        elif data == b"HEARTBEAT-ACK":
            continue

        # clear_last_line()
        print(f"You got message from {addr}: {data.decode()}")


def handle_commands():
    global isPartnerHere
    while True:
        command = input().strip().lower()

        if command == "connect":
            if not isPartnerHere:
                print("Send SYN")
                sock.sendto(b"SYN", (remote_ip, remote_port))
            else:
                print("Already connected.")

        elif command.startswith("send message"):
            if isPartnerHere:
                message = command[len("send message "):]  # Извлекаем текст сообщения
                sock.sendto(message.encode(), (remote_ip, remote_port))
            else:
                print("You are not connected. Use 'connect' to establish a connection.")

        elif command == "disconnect":
            if isPartnerHere:
                # 1. Node 1: FIN → Node 2
                print("Send FIN")
                sock.sendto(b"FIN", (remote_ip, remote_port))
            else:
                print("You are not connected.")

        else:
            print("Invalid command. Available commands: connect, send message <text>, disconnect")


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

local_port = int(input("Enter the port to listen on: "))

remote_ip = "127.0.0.1"

remote_port = int(input("Enter the target node's port: "))

print(f"Sending messages to {remote_ip}:{remote_port}")

sock.bind(("", local_port))

receive_thread = threading.Thread(target=receive_message, args=())
receive_thread.daemon = True
receive_thread.start()

heartbeat_thread = threading.Thread(target=wait_for_heartbeat, args=())
heartbeat_thread.daemon = True
heartbeat_thread.start()


handle_commands()

