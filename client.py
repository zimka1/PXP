import socket
import threading
import time
from queue import Queue
from dataclasses import dataclass
import os

# Defining states
STATE_DISCONNECTED = "DISCONNECTED"  # State: disconnected
STATE_WAIT_SYN_ACK = "WAIT_SYN_ACK"  # State: waiting for SYN-ACK
STATE_CONNECTED = "CONNECTED"  # State: connected
STATE_WAIT_FIN_ACK = "WAIT_FIN_ACK"  # State: waiting for FIN-ACK
STATE_WAIT_ACK = "WAIT_ACK"

# Packet's types
TYPE_MESSAGE = 0x01  # Packet type: message
TYPE_ACK = 0x02  # Packet type: ACK (acknowledgment)
TYPE_SYN = 0x03  # Packet type: SYN (connection request)
TYPE_SYN_ACK = 0x04  # Packet type: SYN-ACK (response to SYN)
TYPE_FIN = 0x05  # Packet type: FIN (connection termination request)
TYPE_FIN_ACK = 0x06  # Packet type: FIN-ACK (final acknowledgment for FIN)
TYPE_HEARTBEAT = 0x07  # Packet type: HEARTBEAT (keep-alive signal)
TYPE_HEARTBEAT_ACK = 0x08  # Packet type: HEARTBEAT-ACK (acknowledgment for HEARTBEAT)
TYPE_NACK = 0x09  # Packet type: NACK (negative acknowledgment)
TYPE_DATA = 0x0A  # Packet type: DATA (file or data transmission)
TYPE_FILENAME = 0x0B
TYPE_FIN_FRAG = 0x0C


state = STATE_DISCONNECTED  # Initial state
heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = 0
areYouAFK = 1

# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue for sending messages
message_queue = Queue()


@dataclass
class ParsedPacket:
    packet_flag: int  # Packet type
    packet_id: int  # Unique packet identifier
    sequence_number: int  # Current fragment number or sequence number
    checksum: int  # Checksum for error detection
    total_length: int  # Total payload length
    payload: str  # Payload (message or data)


@dataclass
class received_message:
    filename: str
    type: int
    message: str
    sequence_number: int
    allIsCorrect: bool


packet_ID = 0
canISendFragments = True
allReceived = True
fragments = [received_message("", 0, "", 0, True) for _ in range(32768)]
total_message = ["" for _ in range(32768)]



def change_state(new_state):
    global state
    state = new_state


# Creates the packet with specified parameters and encodes it to bytes
def create_packet(packet_flag, packet_id, sequence_number, checksum, total_length, payload):
    packet = packet_flag.to_bytes(1, 'big')  # Packet type (1 byte)
    packet += packet_id.to_bytes(2, 'big')  # Packet ID (2 bytes)
    packet += sequence_number.to_bytes(1, 'big')  # Sequence number (1 byte)
    packet += checksum.to_bytes(2, 'big')  # Checksum (2 bytes)
    packet += total_length.to_bytes(2, 'big')  # Total length (2 bytes)
    packet += payload.encode('utf-8')
    return packet


# Sends the packet to the remote node
def send_packet(packet_flag, payload="", packet_id=1, sequence_number=1, checksum=0):
    total_length = len(payload.encode('utf-8'))  # Calculate the total length of the message
    packet = create_packet(packet_flag, packet_id, sequence_number, checksum, total_length, payload)
    sock.sendto(packet, (remote_ip, remote_port))


# Parses the received packet and extracts the header and payload information
def parse_packet(packet):
    packet_flag = int.from_bytes(packet[0:1], 'big')  # Packet type (1 byte)
    packet_id = int.from_bytes(packet[1:3], 'big')  # Packet ID (2 bytes)
    sequence_number = int.from_bytes(packet[3:4], 'big')  # Sequence number (1 byte)
    checksum = int.from_bytes(packet[4:6], 'big')  # Checksum (2 bytes)
    total_length = int.from_bytes(packet[6:8], 'big')  # Total length (2 bytes)
    payload = packet[8:].decode('utf-8')  # Payload (decoded as UTF-8)

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
2. send message (<message>, <length of fragments>) - Send a message to the partner (only available when connected).
3. send file (<file name>, <length of fragments>) - Send a file to the partner (only available when connected).
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
            send_packet(TYPE_FIN)  # Send FIN
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


def wait_for_AFK():
    """
       Checks if the client is inactive (AFK) by waiting for a set interval.
       If the client is active during this period, the function returns False.
       Otherwise, it returns True to indicate the client is AFK.
    """
    global areYouAFK
    areYouAFK = 1
    for i in range(heartbeat_interval):
        time.sleep(1)
        if not areYouAFK:
            return False
    return True


# Continuously monitors for heartbeat signals to keep the connection alive
def wait_for_heartbeat():
    while True:
        if state == STATE_CONNECTED:
            heartbeat_monitor()


# Handles sending and receiving heartbeat packets
def heartbeat_monitor():
    global heartbeat_missed, heartbeat_received
    while state == STATE_CONNECTED:

        if not wait_for_AFK():
            continue

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


def calculate_crc16(data: bytes) -> int:
    # Initialize CRC and define polynomial
    crc = 0xFFFF
    polynomial = 0x1021

    # Iterate over each byte in data
    for byte in data:
        crc ^= byte << 8  # XOR with each byte
        for _ in range(8):
            # Check if the most significant bit is 1
            if crc & 0x8000:
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
            crc &= 0xFFFF  # Ensure it's a 16-bit value
    return crc


def wait_for_ack():
    # Loop until fragments can be sent
    while True:
        if canISendFragments:
            break


def send_file(file_name, fragment_length):
    global packet_ID, state, canISendFragments

    # Increment packet ID for new file
    packet_ID += 1

    # Stores last fragments for potential retransmission
    last_fragments = []
    sequence_number = 0

    # Notify receiver about file name
    send_message(file_name, fragment_length, 'n')

    with open(file_name, "rb") as file:
        while True:
            # Check if all fragments are received
            if allReceived:
                data = file.read(fragment_length)
                # Check if end of file is reached and all fragments are sent
                if not data and sequence_number != 0:
                    send_packet(TYPE_FIN_FRAG, "", packet_ID, sequence_number, 0)
                    canISendFragments = False
                    wait_for_ack()
                    sequence_number = 0
                    continue
                elif not data:
                    send_packet(TYPE_FIN_FRAG, "", packet_ID, sequence_number, 0)
                    break

                # Store fragment and calculate CRC
                last_fragments.append(data)
                crc = calculate_crc16(data)
                sequence_number += 1
                send_packet(TYPE_DATA, data.decode('utf-8'), packet_ID, sequence_number, crc)
                print("send: " + data.decode('utf-8') + " " + str(sequence_number))

                # After sending 6 fragments, wait for acknowledgment
                if sequence_number == 6:
                    canISendFragments = False
                    wait_for_ack()
                    sequence_number = 0
            else:
                # Resend stored fragments if acknowledgment was not received
                for data in last_fragments:
                    crc = calculate_crc16(data)
                    sequence_number += 1
                    send_packet(TYPE_DATA, data.decode('utf-8'), packet_ID, sequence_number, crc)
                    if sequence_number == len(last_fragments):
                        canISendFragments = False
                        wait_for_ack()
                        sequence_number = 0

    print("Partner has all fragments!")


def send_message(message, fragment_length, flag):
    global packet_ID, state, canISendFragments

    # Increment packet ID unless flag is set
    if flag != 'n':
        packet_ID += 1

    # Stores fragments for potential retransmission
    last_fragments = []
    sequence_number = 0
    position = -fragment_length

    while position < len(message):
        if allReceived:
            if position + fragment_length >= len(message) and sequence_number != 0:
                send_packet(TYPE_FIN_FRAG, "", packet_ID, sequence_number, 0)
                canISendFragments = False
                wait_for_ack()
                sequence_number = 0
                continue
            elif position > len(message):
                send_packet(TYPE_FIN_FRAG, "", packet_ID, sequence_number, 0)
                break

            # Prepare and send next fragment
            position += fragment_length
            fragment = message[position:min(position + fragment_length, len(message))]
            last_fragments.append(fragment)
            crc = calculate_crc16(fragment.encode('utf-8'))
            sequence_number += 1

            # Send packet based on flag type (filename or message)
            if flag == 'n':
                send_packet(TYPE_FILENAME, fragment, packet_ID, sequence_number, crc)
            else:
                send_packet(TYPE_MESSAGE, fragment, packet_ID, sequence_number, crc)

            # After sending 6 fragments, wait for acknowledgment
            if sequence_number == 6:
                canISendFragments = False
                wait_for_ack()
                sequence_number = 0
        else:
            # Resend last fragments if acknowledgment was not received
            for fragment in last_fragments:
                crc = calculate_crc16(fragment.encode('utf-8'))
                sequence_number += 1

                if flag == 'n':
                    send_packet(TYPE_FILENAME, fragment, packet_ID, sequence_number, crc)
                else:
                    send_packet(TYPE_MESSAGE, fragment, packet_ID, sequence_number, crc)

                if sequence_number == len(last_fragments):
                    canISendFragments = False
                    wait_for_ack()
                    sequence_number = 0

    # Confirmation of all fragments sent
    if flag != 'n':
        print("Partner has received all fragments!")
    else:
        print("Partner has received all fragments of filename!")


def checkIfSomethingIsWrong(packet):
    # Calculate CRC to verify packet integrity
    calculated_crc = calculate_crc16(packet.payload.encode('utf-8'))

    # If CRC does not match, mark fragment as incorrect
    if calculated_crc != packet.checksum:
        fragments[packet.packet_id].allIsCorrect = False

    # Store packet information in fragments list
    fragments[packet.packet_id].type = packet.packet_flag
    fragments[packet.packet_id].message += packet.payload
    fragments[packet.packet_id].sequence_number += 1

    # After receiving 6 fragments, send ACK or NACK based on correctness
    if fragments[packet.packet_id].sequence_number == 6:
        if fragments[packet.packet_id].allIsCorrect:
            total_message[packet.packet_id] += fragments[packet.packet_id].message
            send_packet(TYPE_ACK)
        else:
            send_packet(TYPE_NACK)
        fragments[packet.packet_id].message = ""
        fragments[packet.packet_id].sequence_number = 0
        fragments[packet.packet_id].allIsCorrect = True


def check_file_exists(file_path):
    # Check if file exists at the given path
    return os.path.isfile(file_path)


def save_data(packet):
    # Verify if fragment is complete and correct, then add to total message
    if fragments[packet.packet_id].message != "" and fragments[packet.packet_id].allIsCorrect:
        total_message[packet.packet_id] += fragments[packet.packet_id].message
        send_packet(TYPE_ACK)
    elif not fragments[packet.packet_id].allIsCorrect:
        send_packet(TYPE_NACK)
        return

    # Handle specific packet types
    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id].filename = total_message[packet.packet_id]
    if fragments[packet.packet_id].type == TYPE_MESSAGE:
        print(f"You got message: {total_message[packet.packet_id]}")
        total_message[packet.packet_id] = ""
    elif fragments[packet.packet_id].type == TYPE_DATA:
        # Generate unique filename for received file
        filename = ""
        for i in range(32768):
            name, filetype = fragments[packet.packet_id].filename.split('.')
            print(i)
            if not i:
                cur_filename = "received_" + name + '.' + filetype
            else:
                cur_filename = "received_" + name + "_" + str(i) + '.' + filetype
            if not check_file_exists(cur_filename):
                filename = cur_filename
                break

        # Save total message content to the determined filename
        with open(filename, "a") as file:
            file.write(total_message[packet.packet_id])

    # Reset total message and fragments after saving
    total_message[packet.packet_id] = ""
    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id] = received_message(fragments[packet.packet_id].filename, 0, "", 0, True)
    else:
        fragments[packet.packet_id] = received_message("", 0, "", 0, True)


# Receives packets and handles the protocol logic for various packet types
def receive_message():
    global heartbeat_received, allReceived, canISendFragments, areYouAFK


    while True:
        data, addr = sock.recvfrom(1024)  # Receive packet

        areYouAFK = 0

        packet = parse_packet(data)

        if packet.packet_flag == TYPE_ACK:
            canISendFragments = True
            allReceived = True
            continue

        if packet.packet_flag == TYPE_NACK:
            canISendFragments = True
            allReceived = False
            continue

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

        if packet.packet_flag == TYPE_DATA or packet.packet_flag == TYPE_MESSAGE or packet.packet_flag == TYPE_FILENAME:
            checkIfSomethingIsWrong(packet)
            continue

        if packet.packet_flag == TYPE_FIN_FRAG:
            save_data(packet)



def handle_commands():
    global areYouAFK

    print("Type 'help' to see the list of available commands.")
    while True:
        command = input().strip().lower()

        if command == "connect" and state == STATE_DISCONNECTED:
            with lock:  # Using lock
                send_packet(TYPE_SYN)
                change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK
            time.sleep(2)
            if state == STATE_WAIT_SYN_ACK:
                print("Connection error.")
                change_state(STATE_DISCONNECTED)

        elif command.startswith("send message") and state == STATE_CONNECTED:
            command = command.replace("send message (", "").replace(")", "")
            message, fragment_length = command.split(", ")
            add_task_to_queue(send_message, message, int(fragment_length), 'm')

        elif command.startswith("send file") and state == STATE_CONNECTED:
            command = command.replace("send file (", "").replace(")", "")
            file_name, fragment_length = command.split(", ")
            add_task_to_queue(send_file, file_name, int(fragment_length))

        elif command == "disconnect" and state == STATE_CONNECTED:
            with lock:
                send_packet(TYPE_FIN)
                change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK

        elif command == "help":
            show_help()
            continue
        else:
            print("Invalid command or inappropriate state. Type 'help' for the list of available commands.")
            continue

        areYouAFK = 0

def add_task_to_queue(task, *args):
    message_queue.put((task, args))

def process_message_queue():
    while True:
        if not message_queue.empty():
            if state == STATE_CONNECTED:  # Sending messages only in the CONNECTED state
                task, args = message_queue.get()
                task(*args)


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