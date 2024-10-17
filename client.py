import socket
import threading
import time
from queue import Queue

# Defining states
STATE_INITIAL = "INITIAL"
STATE_WAIT_SYN_ACK = "WAIT_SYN_ACK"
STATE_CONNECTED = "CONNECTED"
STATE_WAIT_FIN_ACK = "WAIT_FIN_ACK"

state = STATE_INITIAL  # Initial state
isPartnerHere = 0
heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = 0

# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue
message_queue = Queue()

def show_help():
    print("""
Available commands:
1. connect - Initiate connection to the partner.
2. send message <text> - Send a message to the partner (only available when connected).
3. disconnect - Gracefully disconnect from the partner.
4. help - Show this list of commands.
""")

def change_state(new_state):
    global state
    # print(f"Changing state from {state} to {new_state}")
    state = new_state

def receive_handshake(addr):
    global isPartnerHere
    with lock:
        # print("Received SYN")
        if state == STATE_INITIAL:
            sock.sendto(b"SYN-ACK", addr)
            change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK
            data, addr = sock.recvfrom(1024)
            if data == b"ACK":
                print("Handshake complete.")
                isPartnerHere = 1
                change_state(STATE_CONNECTED)  # Transition to CONNECTED state

def continue_handshake():
    global isPartnerHere
    with lock:
        if state == STATE_WAIT_SYN_ACK:
            # print("Received SYN-ACK, sending ACK")
            sock.sendto(b"ACK", (remote_ip, remote_port))
            print("Handshake complete.")
            isPartnerHere = 1
            change_state(STATE_CONNECTED)  # Transition to CONNECTED state

def receive_termination(addr):
    global isPartnerHere
    with lock:
        if state == STATE_CONNECTED:
            # print("Received FIN")
            sock.sendto(b"FIN-ACK", addr)  # 2. Node 2: ACK → Node 1
            sock.sendto(b"FIN", addr)  # 3. Node 2: FIN → Node 1
            change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK
            data, addr = sock.recvfrom(1024)
            if data == b"ACK":
                isPartnerHere = 0
                print("Connection terminated.")
                change_state(STATE_INITIAL)  # Transition to INITIAL state

def continue_termination():
    global isPartnerHere
    with lock:
        if state == STATE_WAIT_FIN_ACK:
            # print("Received ACK, waiting for FIN")
            data, addr = sock.recvfrom(1024)
            if data == b"FIN":
                # print("Received FIN, sending final ACK")
                sock.sendto(b"ACK", addr)  # 4. Node 1: ACK → Node 2
                print("Connection terminated.")
                isPartnerHere = 0
                change_state(STATE_INITIAL)  # Transition to INITIAL state

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
            # print("All good!")
        else:
            heartbeat_missed += 1

        heartbeat_received = 0

        if heartbeat_missed >= max_missed_heartbeats:
            print("Connection lost. No response from the partner.")
            heartbeat_missed = 0
            isPartnerHere = 0
            change_state(STATE_INITIAL)
            break

def receive_message():
    global heartbeat_received

    while True:
        data, addr = sock.recvfrom(1024)

        # if someone wants to reconnect
        if data == b"SYN":
            receive_handshake(addr)
            continue

        if data == b"SYN-ACK":
            continue_handshake()
            continue

        # if someone wants to disconnect
        if data == b"FIN":
            receive_termination(addr)
            continue

        if data == b"FIN-ACK":
            continue_termination()
            continue

        if data == b"HEARTBEAT" and isPartnerHere == 1:
            # print("Received HEARTBEAT")
            sock.sendto(b"HEARTBEAT-ACK", addr)
            continue
        elif data == b"HEARTBEAT":
            continue

        if data == b"HEARTBEAT-ACK" and isPartnerHere == 1:
            # print("Received HEARTBEAT-ACK")
            heartbeat_received = 1
            continue
        elif data == b"HEARTBEAT-ACK":
            continue

        print(f"You got message from {addr}: {data.decode()}")

def handle_commands():
    global isPartnerHere
    print("Type 'help' to see the list of available commands.")
    while True:
        command = input().strip().lower()

        if command == "connect" and state == STATE_INITIAL:
            # print("Send SYN")
            with lock:  # Using lock
                sock.sendto(b"SYN", (remote_ip, remote_port))
                change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK

        elif command.startswith("send message") and state == STATE_CONNECTED:
            message = command[len("send message "):]  # Extracting message text
            message_queue.put(message)  # Putting the message into the queue

        elif command == "disconnect" and state == STATE_CONNECTED:
            with lock:
                print("Send FIN")
                sock.sendto(b"FIN", (remote_ip, remote_port))
                change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK

        elif command == "help":
            show_help()

        else:
            print("Invalid command or inappropriate state. Type 'help' for the list of available commands.")

def process_message_queue():
    while True:
        if not message_queue.empty():
            if state == STATE_CONNECTED:  # Sending messages only in the CONNECTED state
                message = message_queue.get()
                print(f"Sending message: {message}")
                sock.sendto(message.encode(), (remote_ip, remote_port))


# Network settings
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
local_port = int(input("Enter the port to listen on: "))
remote_ip = "127.0.0.1"
remote_port = int(input("Enter the target node's port: "))
print(f"Sending messages to {remote_ip}:{remote_port}")
sock.bind(("", local_port))

# Thread for receiving messages
receive_thread = threading.Thread(target=receive_message, args=())
receive_thread.daemon = True
receive_thread.start()

# Thread for Heartbeat
heartbeat_thread = threading.Thread(target=wait_for_heartbeat, args=())
heartbeat_thread.daemon = True
heartbeat_thread.start()

# Thread for processing message queue
message_thread = threading.Thread(target=process_message_queue, args=())
message_thread.daemon = True
message_thread.start()

# Command handler
handle_commands()
