import socket
import threading
import time
from queue import Queue
from dataclasses import dataclass

# Defining states
STATE_INITIAL = "INITIAL"
STATE_WAIT_SYN_ACK = "WAIT_SYN_ACK"
STATE_CONNECTED = "CONNECTED"
STATE_WAIT_FIN_ACK = "WAIT_FIN_ACK"

# Packet's types
TYPE_MESSAGE = 0x01
TYPE_ACK = 0x02
TYPE_SYN = 0x03
TYPE_SYN_ACK = 0x04
TYPE_FIN = 0x05
TYPE_FIN_ACK = 0x06
TYPE_HEARTBEAT = 0x07
TYPE_HEARTBEAT_ACK = 0x08

state = STATE_INITIAL  # Initial state
heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = 0


# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue
message_queue = Queue()

@dataclass
class ParsedPacket:
    packet_type: int        # Packet type
    packet_id: int          # Unique packet identifier
    total_length: int       # Total message length
    fragment_number: int    # Current fragment number
    total_fragments: int    # Total number of fragments
    payload: str            # Payload (message or data)


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


def create_packet(packet_type, total_length, fragment_number, total_fragments, packet_id, payload):

    packet = f"{packet_type}:{packet_id}:{total_length}:{fragment_number}:{total_fragments}:{payload}"
    return packet.encode('utf-8')



def send_packet(packet_type, message="", fragment_number=0, total_fragments=0, packet_id=0):
    packet = create_packet(packet_type, len(message),fragment_number, total_fragments, packet_id, message)
    sock.sendto(packet, (remote_ip, remote_port))


def parse_packet(packet):
    packet = packet.decode('utf-8')  # Декодируем пакет из байтов в строку
    parts = packet.split(':')

    # Преобразуем части пакета в нужные типы
    packet_type = int(parts[0])
    packet_id = int(parts[1])
    total_length = int(parts[2])
    fragment_number = int(parts[3])
    total_fragments = int(parts[4])
    payload = parts[5]

    return ParsedPacket(
        packet_type=packet_type,
        packet_id=packet_id,
        total_length=total_length,
        fragment_number=fragment_number,
        total_fragments=total_fragments,
        payload=payload
    )


def receive_handshake():
    with lock:
        # print("Received SYN")
        if state == STATE_INITIAL:
            send_packet(TYPE_SYN_ACK)

            change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK

            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)

            if packet.packet_type == TYPE_ACK:
                print("Handshake complete.")
                change_state(STATE_CONNECTED)  # Transition to CONNECTED state

def continue_handshake():
    with lock:
        if state == STATE_WAIT_SYN_ACK:
            # print("Received SYN-ACK, sending ACK")
            send_packet(TYPE_ACK)
            print("Handshake complete.")
            change_state(STATE_CONNECTED)  # Transition to CONNECTED state

def receive_termination():
    with lock:
        if state == STATE_CONNECTED:
            # print("Received FIN")
            send_packet(TYPE_FIN_ACK)  # 2. Node 2: FIN-ACK → Node 1
            send_packet(TYPE_FIN)  # 3. Node 2: FIN → Node 1
            change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)
            if packet.packet_type == TYPE_ACK:
                print("Connection terminated.")
                change_state(STATE_INITIAL)  # Transition to INITIAL state

def continue_termination():
    with lock:
        if state == STATE_WAIT_FIN_ACK:
            # print("Received ACK, waiting for FIN")
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)
            if packet.packet_type == TYPE_FIN:
                # print("Received FIN, sending final ACK")
                send_packet(TYPE_ACK)  # 4. Node 1: ACK → Node 2
                print("Connection terminated.")
                change_state(STATE_INITIAL)  # Transition to INITIAL state

def wait_for_heartbeat():
    while True:
        if state == STATE_CONNECTED:
            heartbeat_monitor()

def heartbeat_monitor():
    global heartbeat_missed, heartbeat_received
    while state == STATE_CONNECTED:
        time.sleep(heartbeat_interval)

        send_packet(TYPE_HEARTBEAT)

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
            change_state(STATE_INITIAL)
            break

def receive_message():
    global heartbeat_received

    while True:
        data, addr = sock.recvfrom(1024)

        packet = parse_packet(data)

        # if someone wants to reconnect
        if packet.packet_type == TYPE_SYN:
            receive_handshake()
            continue

        if packet.packet_type == TYPE_SYN_ACK:
            continue_handshake()
            continue

        # if someone wants to disconnect
        if packet.packet_type == TYPE_FIN:
            receive_termination()
            continue

        if packet.packet_type == TYPE_FIN_ACK:
            continue_termination()
            continue

        if packet.packet_type == TYPE_HEARTBEAT and state == STATE_CONNECTED:
            # print("Received HEARTBEAT")
            send_packet(TYPE_HEARTBEAT_ACK)
            continue
        elif packet.packet_type == TYPE_HEARTBEAT:
            continue

        if packet.packet_type == TYPE_HEARTBEAT_ACK and state == STATE_CONNECTED:
            # print("Received HEARTBEAT-ACK")
            heartbeat_received = 1
            continue
        elif packet.packet_type == TYPE_HEARTBEAT_ACK:
            continue

        print(f"You got message from {addr}: {packet.payload}")

def handle_commands():
    global isPartnerHere
    print("Type 'help' to see the list of available commands.")
    while True:
        command = input().strip().lower()

        if command == "connect" and state == STATE_INITIAL:
            # print("Send SYN")
            with lock:  # Using lock
                send_packet(TYPE_SYN)
                change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK

        elif command.startswith("send message") and state == STATE_CONNECTED:
            message = command[len("send message "):]  # Extracting message text
            message_queue.put(message)  # Putting the message into the queue

        elif command == "disconnect" and state == STATE_CONNECTED:
            with lock:
                # print("Send FIN")
                send_packet(TYPE_FIN)
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
                send_packet(TYPE_MESSAGE, message)


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
