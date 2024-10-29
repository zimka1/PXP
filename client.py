import socket
import threading
import time
from queue import Queue
from dataclasses import dataclass

# Defining states
STATE_DISCONNECTED = "DISCONNECTED"   # State: disconnected
STATE_WAIT_SYN_ACK = "WAIT_SYN_ACK"   # State: waiting for SYN-ACK
STATE_CONNECTED = "CONNECTED"         # State: connected
STATE_WAIT_FIN_ACK = "WAIT_FIN_ACK"   # State: waiting for FIN-ACK

# Packet's types
TYPE_MESSAGE = 0x01       # Packet type: message
TYPE_ACK = 0x02           # Packet type: ACK (acknowledgment)
TYPE_SYN = 0x03           # Packet type: SYN (connection request)
TYPE_SYN_ACK = 0x04       # Packet type: SYN-ACK (response to SYN)
TYPE_FIN = 0x05           # Packet type: FIN (connection termination request)
TYPE_FIN_ACK = 0x06       # Packet type: FIN-ACK (final acknowledgment for FIN)
TYPE_HEARTBEAT = 0x07     # Packet type: HEARTBEAT (keep-alive signal)
TYPE_HEARTBEAT_ACK = 0x08 # Packet type: HEARTBEAT-ACK (acknowledgment for HEARTBEAT)
TYPE_NACK = 0x09          # Packet type: NACK (negative acknowledgment)
TYPE_DATA = 0x0A          # Packet type: DATA (file or data transmission)

state = STATE_DISCONNECTED  # Initial state
heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = 0

# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue for sending messages
message_queue = Queue()

@dataclass
class ParsedPacket:
    packet_flag: int        # Packet type
    packet_id: int          # Unique packet identifier
    sequence_number: int    # Current fragment number or sequence number
    checksum: int           # Checksum for error detection
    total_length: int       # Total payload length
    payload: str            # Payload (message or data)


def change_state(new_state):
    global state
    state = new_state


# Creates the packet with specified parameters and encodes it to bytes
def create_packet(packet_flag, packet_id, sequence_number, checksum, total_length, payload):
    packet = packet_flag.to_bytes(1, 'big')        # Packet type (1 byte)
    packet += packet_id.to_bytes(2, 'big')         # Packet ID (2 bytes)
    packet += sequence_number.to_bytes(1, 'big')   # Sequence number (1 byte)
    packet += checksum.to_bytes(2, 'big')          # Checksum (2 bytes)
    packet += total_length.to_bytes(2, 'big')      # Total length (2 bytes)
    packet += payload.encode('utf-8')              # Payload (message or data, UTF-8 encoded)
    return packet


# Sends the packet to the remote node
def send_packet(packet_flag, message="", sequence_number=1, packet_id=1, checksum=0):
    total_length = len(message.encode('utf-8'))  # Calculate the total length of the message
    packet = create_packet(packet_flag, packet_id, sequence_number, checksum, total_length, message)
    sock.sendto(packet, (remote_ip, remote_port))


# Parses the received packet and extracts the header and payload information
def parse_packet(packet):
    packet_flag = int.from_bytes(packet[0:1], 'big')  # Packet type (1 byte)
    packet_id = int.from_bytes(packet[1:3], 'big')    # Packet ID (2 bytes)
    sequence_number = int.from_bytes(packet[3:4], 'big')   # Sequence number (1 byte)
    checksum = int.from_bytes(packet[4:6], 'big')     # Checksum (2 bytes)
    total_length = int.from_bytes(packet[6:8], 'big') # Total length (2 bytes)
    payload = packet[8:].decode('utf-8')              # Payload (decoded as UTF-8)

    return ParsedPacket(
        packet_flag=packet_flag,
        packet_id=packet_id,
        sequence_number=sequence_number,
        checksum=checksum,
        total_length=total_length,
        payload=payload
    )


# Displays available commands to the user
def show_help():
    print("""
Available commands:
1. connect - Initiate connection to the partner.
2. send message <text> - Send a message to the partner (only available when connected).
3. disconnect - Gracefully disconnect from the partner.
4. help - Show this list of commands.
""")


# Receives SYN and completes the handshake by sending SYN-ACK
def receive_handshake():
    with lock:
        if state == STATE_DISCONNECTED:
            send_packet(TYPE_SYN_ACK)  # Send SYN-ACK
            change_state(STATE_WAIT_SYN_ACK)  # Move to WAIT_SYN_ACK state

            # Wait for ACK
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)

            if packet.packet_flag == TYPE_ACK:  # ACK received, handshake complete
                print("Handshake complete.")
                change_state(STATE_CONNECTED)  # Move to CONNECTED state

# Sends SYN and waits for SYN-ACK to complete the handshake
def continue_handshake():
    with lock:
        if state == STATE_WAIT_SYN_ACK:
            send_packet(TYPE_ACK)  # Send ACK
            print("Handshake complete.")
            change_state(STATE_CONNECTED)  # Move to CONNECTED state


# Receives FIN request and completes the disconnection process
def receive_termination():
    with lock:
        if state == STATE_CONNECTED:
            send_packet(TYPE_FIN_ACK)  # Send FIN-ACK
            send_packet(TYPE_FIN)      # Send FIN
            change_state(STATE_WAIT_FIN_ACK)  # Move to WAIT_FIN_ACK state

            # Wait for final ACK
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)
            if packet.packet_flag == TYPE_ACK:  # Connection termination complete
                print("Connection terminated.")
                change_state(STATE_DISCONNECTED)  # Move back to DISCONNECTED state


# Completes the termination by sending the final ACK
def continue_termination():
    with lock:
        if state == STATE_WAIT_FIN_ACK:
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)
            if packet.packet_flag == TYPE_FIN:
                send_packet(TYPE_ACK)  # Send final ACK
                print("Connection terminated.")
                change_state(STATE_DISCONNECTED)  # Return to DISCONNECTED state


# Continuously monitors for heartbeat signals to keep the connection alive
def wait_for_heartbeat():
    while True:
        if state == STATE_CONNECTED:
            heartbeat_monitor()

# Handles sending and receiving heartbeat packets
def heartbeat_monitor():
    global heartbeat_missed, heartbeat_received
    while state == STATE_CONNECTED:
        time.sleep(heartbeat_interval)

        send_packet(TYPE_HEARTBEAT)  # Send HEARTBEAT

        time.sleep(heartbeat_interval_to_ans)

        if heartbeat_received:
            heartbeat_missed = 0  # Reset missed heartbeats
        else:
            heartbeat_missed += 1  # Increment missed heartbeats count

        heartbeat_received = 0

        if heartbeat_missed >= max_missed_heartbeats:
            print("Connection lost. No response from the partner.")
            heartbeat_missed = 0
            change_state(STATE_DISCONNECTED)
            break


# Receives packets and handles the protocol logic for various packet types
def receive_message():
    global heartbeat_received

    while True:
        data, addr = sock.recvfrom(1024)  # Receive packet

        packet = parse_packet(data)

        # Handle incoming SYN packet (connection request)
        if packet.packet_flag == TYPE_SYN:
            receive_handshake()
            continue

        # Handle incoming SYN-ACK (handshake continuation)
        if packet.packet_flag == TYPE_SYN_ACK:
            continue_handshake()
            continue

        # Handle incoming FIN packet (connection termination request)
        if packet.packet_flag == TYPE_FIN:
            receive_termination()
            continue

        # Handle incoming FIN-ACK (final ACK for termination)
        if packet.packet_flag == TYPE_FIN_ACK:
            continue_termination()
            continue

        # Handle heartbeat packets to maintain connection health
        if packet.packet_flag == TYPE_HEARTBEAT and state == STATE_CONNECTED:
            send_packet(TYPE_HEARTBEAT_ACK)  # Send HEARTBEAT-ACK
            continue
        elif packet.packet_flag == TYPE_HEARTBEAT:
            continue

        if packet.packet_flag == TYPE_HEARTBEAT_ACK and state == STATE_CONNECTED:
            heartbeat_received = 1  # Acknowledge received heartbeat
            continue
        elif packet.packet_flag == TYPE_HEARTBEAT_ACK:
            continue

        print(f"You got message from {addr}: {packet.payload}")  # Print received message

def handle_commands():
    print("Type 'help' to see the list of available commands.")
    while True:
        command = input().strip().lower()

        if command == "connect" and state == STATE_DISCONNECTED:
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
remote_ip = input ("Enter the remote node’s IP address : ")
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
