import socket
import threading
import time
from queue import Queue
from dataclasses import dataclass, field
import os
import random
from typing import List
import math

# Defining states
STATE_DISCONNECTED = "DISCONNECTED"  # State: disconnected
STATE_WAIT_SYN_ACK = "WAIT_SYN_ACK"  # State: waiting for SYN-ACK
STATE_CONNECTED = "CONNECTED"  # State: connected
STATE_WAIT_FIN_ACK = "WAIT_FIN_ACK"  # State: waiting for FIN-ACK
STATE_WAIT_ACK = "WAIT_ACK"

ORDINARY_MODE = "ORDINARY"
LOSS_MODE = "LOSS"

# Packet's types
TYPE_MESSAGE = 0x01  # Packet type: message
TYPE_DATA = 0x02  # Packet type: DATA (file or data transmission)
TYPE_FILENAME = 0x03
TYPE_MAKE_MONITOR = 0x04
TYPE_FIN_FRAG = 0x05
TYPE_CHECK = 0x06
TYPE_ACK = 0x07  # Packet type: ACK (acknowledgment)
TYPE_NACK = 0x08  # Packet type: NACK (negative acknowledgment)
TYPE_SYN = 0x09  # Packet type: SYN (connection request)
TYPE_SYN_ACK = 0x0A  # Packet type: SYN-ACK (response to SYN)
TYPE_FIN = 0x0B  # Packet type: FIN (connection termination request)
TYPE_FIN_ACK = 0x0C  # Packet type: FIN-ACK (final acknowledgment for FIN)
TYPE_HEARTBEAT = 0x0D  # Packet type: HEARTBEAT (keep-alive signal)
TYPE_HEARTBEAT_ACK = 0x0E  # Packet type: HEARTBEAT-ACK (acknowledgment for HEARTBEAT)

state = STATE_DISCONNECTED  # Initial state
mode = ORDINARY_MODE # Initial mode

heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = False
areYouAFK = 1

sent_packets = []
missed_packets = []
first_fragment_come = False
time_fragment_come = time.time()
dont_should_wait = True

# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue for sending messages
message_queue = Queue()


@dataclass
class ParsedPacket:
    packet_flag: int  # Packet type
    packet_id: int  # Unique packet identifier
    sequence_number: int  # Current fragment number or sequence number
    acknowledgment_number: int  # Total payload length
    checksum: int  # Checksum for error detection
    payload: bytes  # Payload (message or data)

last_fragment_packet = None

@dataclass
class received_message:
    filename: str
    type: int
    array: List = field(default_factory=list)

packet_ID = 0
canISendFragments = True
allReceived = True
fragments = [received_message("", 0, []) for _ in range(32768)]
total_message = [b"" for _ in range(32768)]


window_size = 0
max_window_size = 0
min_window_size = 6
alpha = 0
beta = 0


def change_state(new_state):
    global state
    state = new_state

def change_mode(new_mode):
    global mode
    mode = new_mode

# Creates the packet with specified parameters and encodes it to bytes
def create_packet(packet_flag, packet_id, sequence_number, acknowledgment_number, checksum, payload):
    packet = packet_flag.to_bytes(1, 'big')  # Packet type (1 byte)
    packet += packet_id.to_bytes(2, 'big')  # Packet ID (2 bytes)
    packet += sequence_number.to_bytes(3, 'big')  # Sequence number (3 byte)
    packet += acknowledgment_number.to_bytes(3, 'big')  # Total length (3 bytes)
    packet += checksum.to_bytes(4, 'big')  # Checksum (3 bytes)
    packet += payload
    return packet


# Sends the packet to the remote node
def send_packet(packet_flag, packet_id=0, sequence_number=0, acknowledgment_number=0, checksum=0, payload='0'.encode('utf-8')):
    packet = create_packet(packet_flag, packet_id, sequence_number, acknowledgment_number, checksum, payload)
    sock.sendto(packet, (remote_ip, remote_port))


# Parses the received packet and extracts the header and payload information
def parse_packet(packet):
    packet_flag = int.from_bytes(packet[0:1], 'big')  # Packet type (1 byte)
    packet_id = int.from_bytes(packet[1:3], 'big')  # Packet ID (2 bytes)
    sequence_number = int.from_bytes(packet[3:6], 'big')  # Sequence number (1 byte)
    acknowledgment_number = int.from_bytes(packet[6:9], 'big')
    checksum = int.from_bytes(packet[9:13], 'big')  # Checksum (4 bytes)
    payload = packet[13:] # Payload (decoded as UTF-8)

    return ParsedPacket(
        packet_flag=packet_flag,
        packet_id=packet_id,
        sequence_number=sequence_number,
        acknowledgment_number=acknowledgment_number,
        checksum=checksum,
        payload=payload
    )


# Displays available commands to the user
def show_help():
    blue_text = "\033[94m"
    reset_text = "\033[0m"
    red_text = "\033[91m"
    yellow_text = "\033[93m"
    green_text = "\033[92m"

    print(f"""
{green_text}Available commands:
{yellow_text}1. {blue_text}help{reset_text} - Show this list of commands.
{yellow_text}2. {blue_text}connect{reset_text} - Initiate connection to the partner.
{yellow_text}3. {blue_text}disconnect{reset_text} - Gracefully disconnect from the partner.
{yellow_text}4. {blue_text}change mode{reset_text} - Enable or Disable packet loss simulation during transmission {red_text}(only available when connected).{reset_text}
{yellow_text}5. {blue_text}send message (<message>, <length of fragments>){reset_text} - Send a message in fragments to the partner {red_text}(only available when connected).{reset_text}
{yellow_text}6. {blue_text}send message (<message>){reset_text} - Send a message {red_text}NOT{reset_text} in fragments to the partner {red_text}(only available when connected).{reset_text}
{yellow_text}7. {blue_text}send file (<file name>, <length of fragments>){reset_text} - Send a file in fragments to the partner {red_text}(only available when connected).{reset_text}
{yellow_text}8. {blue_text}send file (<file name>){reset_text} - Send a file {red_text}NOT{reset_text} in fragments to the partner {red_text}(only available when connected).{reset_text}
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

# Checks if the client is inactive (AFK) by waiting for a set interval.
def wait_for_AFK():
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

        heartbeat_received = False

        if heartbeat_missed >= max_missed_heartbeats:
            print("Connection lost. No response from the partner.")
            heartbeat_missed = 0
            change_state(STATE_DISCONNECTED)
            break


def calculate_crc32(data: bytes) -> int:
    # Initialize CRC and polynomial for 32-bit
    crc = 0xFFFFFFFF  # Инициализация 32-битного значения CRC
    polynomial = 0x04C11DB7  # Стандартный полином для CRC32

    # Process each byte in the data
    for byte in data:
        crc ^= byte << 24  # XOR с каждым байтом, сдвинутым на 24 бита
        for _ in range(8):
            if crc & 0x80000000:  # Если старший бит (32-й) равен 1
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF  # Обеспечение 32-битного значения

    return crc

def wait_for_ack():
    # Loop until fragments can be sent
    while True:
        if canISendFragments or state == STATE_DISCONNECTED:
            break


def should_drop_or_damage_packet(probability):
    return random.random() < probability and mode == LOSS_MODE

def damage_packet(crc):
    return crc ^ 0x1


def send_again():
    global allReceived, missed_packets, canISendFragments
    time.sleep(0.5)
    for sequence_number_of_missed_packet in missed_packets:
        for sent_packet in sent_packets:
            parsed_sent_packet = parse_packet(sent_packet)
            # print(parsed_sent_packet)
            if parsed_sent_packet.sequence_number == sequence_number_of_missed_packet:
                print(
                    f"sent again: {parsed_sent_packet.payload} sequence: {sequence_number_of_missed_packet}")
                send_packet(parsed_sent_packet.packet_flag,
                            parsed_sent_packet.packet_id, parsed_sent_packet.sequence_number, 0,
                            parsed_sent_packet.checksum, parsed_sent_packet.payload)
                break

    allReceived = True
    missed_packets = []

    canISendFragments = False

def on_successful_ack():
    global window_size
    if window_size <= max_window_size:
        window_size = min(int(window_size + alpha), max_window_size)

def on_packet_loss():
    global window_size
    window_size = max(int(window_size - beta), min_window_size)

def set_window_settings(total_length, fragment_length):
    global max_window_size, min_window_size, window_size, alpha, beta

    min_window_size = max(math.ceil(0.1 * math.ceil(total_length / fragment_length)), 6)

    max_window_size = max(math.ceil(0.5 * math.ceil(total_length / fragment_length)), min_window_size)

    alpha = math.ceil(0.125 * math.ceil(total_length / fragment_length))
    beta = math.ceil(0.125 * math.ceil(total_length / fragment_length))

    window_size = min_window_size
    print(window_size, max_window_size, min_window_size)

def send_file(file_name, fragment_length):
    global packet_ID, state, canISendFragments, allReceived, missed_packets, sent_packets

    packet_ID += 1

    sequence_number = -1
    window_number = 0

    with open(file_name, "rb") as file:
        content = file.read()
        total_length = len(content)

    send_message(file_name, len(file_name) if total_length == fragment_length else fragment_length, 'n')

    set_window_settings(total_length, fragment_length)

    with open(file_name, "rb") as file:
        data = file.read(fragment_length)
        while True:
            if allReceived:
                if not data:
                    break

                crc = calculate_crc32(data)
                sequence_number += 1
                window_number += 1

                how_much_left = max(math.ceil((total_length - sequence_number * fragment_length) / fragment_length), 1)

                acknowledgment_number = min(window_size, how_much_left)
                print(acknowledgment_number)
                send_packet(TYPE_MAKE_MONITOR, packet_ID, 0, acknowledgment_number)

                print(f"sequence: {sequence_number} window: {window_number} checksum: {crc}")

                if not should_drop_or_damage_packet(0.1):
                    send_packet(TYPE_DATA, packet_ID, sequence_number,0, crc if not should_drop_or_damage_packet(0.1) else damage_packet(crc), data)
                else:
                    print("Packet dropped!")
                packet = create_packet(TYPE_DATA, packet_ID, sequence_number, 0, crc, data)
                sent_packets.append(packet)

                data = file.read(fragment_length)

                print(data)

                if window_number == window_size or (not data and window_number != 0):
                    canISendFragments = False
                    wait_for_ack()
                    if state == STATE_DISCONNECTED:
                        return
                    window_number = 0
                    if allReceived:
                        on_successful_ack()
                    else:
                        on_packet_loss()
            else:
                print(f"missed packets: {missed_packets}")
                print(sent_packets)

                send_again()

                wait_for_ack()
                if state == STATE_DISCONNECTED:
                    return


    print("send FIN_FRAG, without ack")
    send_packet(TYPE_FIN_FRAG, packet_ID, 0, window_number)

    sent_packets = []

    print("Partner has all fragments!")


def send_message(message, fragment_length, flag):
    global packet_ID, state, canISendFragments, allReceived, missed_packets, sent_packets

    if flag != 'n':
        packet_ID += 1

    sequence_number = -1
    window_number = 0
    position = -fragment_length

    total_length = len(message)

    set_window_settings(total_length, fragment_length)

    while position < total_length:
        if allReceived:
            if position + fragment_length >= total_length:
                break

            position += fragment_length
            fragment = message[position:min(position + fragment_length, total_length)].encode('utf-8')
            crc = calculate_crc32(fragment)
            sequence_number += 1
            window_number += 1


            how_much_left = max(math.ceil((total_length - sequence_number * fragment_length) / fragment_length), 1)

            acknowledgment_number = min(window_size, how_much_left)

            send_packet(TYPE_MAKE_MONITOR, packet_ID, 0, acknowledgment_number)

            print(f"sent: {fragment} sequence: {sequence_number}")

            if not should_drop_or_damage_packet(0.1):
                send_packet(TYPE_FILENAME if flag == 'n' else TYPE_MESSAGE, packet_ID, sequence_number, 0, crc if not should_drop_or_damage_packet(0.1) else damage_packet(crc), fragment)
            else:
                print("Packet dropped!")
            packet = create_packet(TYPE_FILENAME if flag == 'n' else TYPE_MESSAGE, packet_ID, sequence_number, 0, crc, fragment)
            sent_packets.append(packet)

            if window_number == window_size or (position + fragment_length >= total_length and window_number != 0):
                canISendFragments = False
                wait_for_ack()
                if state == STATE_DISCONNECTED:
                    return
                window_number = 0
                if allReceived:
                    on_successful_ack()
                else:
                    on_packet_loss()
        else:
            print(f"missed packets: {missed_packets}")
            # print(sent_packets)

            send_again()

            wait_for_ack()
            if state == STATE_DISCONNECTED:
                return

    print("send FIN_FRAG, without ack")
    send_packet(TYPE_FIN_FRAG, packet_ID, 0, window_number)

    sent_packets = []

    if flag != 'n':
        print("Partner has received all fragments!")
    else:
        print("Partner has received all fragments of filename!")


def check_fragments(frags_array):
    for fragment in frags_array:
        if not fragment:
            return False
    return True


def checkIfSomethingIsWrong(packet):
    global first_fragment_come

    if packet.packet_flag == TYPE_MAKE_MONITOR:
        if None not in fragments[packet.packet_id].array:
            fragments[packet.packet_id].array.extend([None] * packet.acknowledgment_number)
        return

    if packet.packet_flag != TYPE_CHECK:
        calculated_crc = calculate_crc32(packet.payload)
        fragments[packet.packet_id].type = packet.packet_flag

        print(f"seq {packet.sequence_number}")

        if calculated_crc == packet.checksum:
            print(calculated_crc, packet.checksum)
            fragments[packet.packet_id].array[packet.sequence_number] = packet.payload
        else:
            print(f"Fragment {packet.sequence_number} is damaged")
            print(calculated_crc, packet.checksum)

    if packet.packet_flag == TYPE_CHECK:
        if check_fragments(fragments[packet.packet_id].array):
            send_packet(TYPE_ACK)
        else:
            missed = ""
            for i,fragment in enumerate(fragments[packet.packet_id].array):
                if not fragment:
                    missed += str(i) + " "
            send_packet(TYPE_NACK, packet.packet_id, 0, 0, packet.checksum, missed.encode('utf-8'))


def should_wait_for_fragment():
    global last_fragment_packet, time_fragment_come, first_fragment_come
    while True:
        if first_fragment_come:
            current_time = time.time()
            while current_time - time_fragment_come < 1:
                if not first_fragment_come:
                    break
                current_time = time.time()
            if first_fragment_come:
                print("send Check!")
                packet = ParsedPacket(TYPE_CHECK, last_fragment_packet.packet_id, 0, 0, 0, "0".encode('utf-8'))
                checkIfSomethingIsWrong(packet)
                first_fragment_come = False



def check_file_exists(file_path):
    # Check if file exists at the given path
    return os.path.isfile(file_path)


def save_data(packet):
    global first_fragment_come

    total_message[packet.packet_id] += b''.join(frag for frag in fragments[packet.packet_id].array)

    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id].filename = total_message[packet.packet_id].decode('utf-8')
    if fragments[packet.packet_id].type == TYPE_MESSAGE:
        print(f"You got message: {total_message[packet.packet_id].decode('utf-8')}")
    elif fragments[packet.packet_id].type == TYPE_DATA:
        # Generate unique filename for received file
        filename = ""
        for i in range(32768):
            name, filetype = fragments[packet.packet_id].filename.split('.')
            if not i:
                cur_filename = "received_" + name + '.' + filetype
            else:
                cur_filename = "received_" + name + "_" + str(i) + '.' + filetype
            if not check_file_exists(cur_filename):
                filename = cur_filename
                break
        # Save total message content to the determined filename
        with open(filename, "ab") as file:
            file.write(total_message[packet.packet_id])

        print(f"You got file: {fragments[packet.packet_id].filename}")

    # Reset total message and fragments after saving
    total_message[packet.packet_id] = b""
    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id] = received_message(fragments[packet.packet_id].filename, TYPE_DATA, [])


# Receives packets and handles the protocol logic for various packet types
def receive_message():
    global heartbeat_received, allReceived, canISendFragments, areYouAFK, last_fragment_packet, time_fragment_come, first_fragment_come, missed_packets

    while True:
        data, addr = sock.recvfrom(1500)  # Receive packet

        areYouAFK = 0

        packet = parse_packet(data)

        if packet.packet_flag == TYPE_ACK:
            canISendFragments = True
            allReceived = True
            continue

        if packet.packet_flag == TYPE_NACK:
            canISendFragments = True
            allReceived = False
            missed_packets = [int(c) for c in packet.payload.decode('utf-8').split(' ') if c.strip()]
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
            heartbeat_received = True  # Acknowledge received heartbeat
            continue
        elif packet.packet_flag == TYPE_HEARTBEAT_ACK:
            continue

        if packet.packet_flag == TYPE_DATA or packet.packet_flag == TYPE_MESSAGE or packet.packet_flag == TYPE_FILENAME or packet.packet_flag == TYPE_MAKE_MONITOR:
            last_fragment_packet = packet
            first_fragment_come = True
            time_fragment_come = time.time()
            print(f"VAAAAA {first_fragment_come}")
            checkIfSomethingIsWrong(packet)
            continue

        if packet.packet_flag == TYPE_FIN_FRAG:
            first_fragment_come = False
            save_data(packet)


def handle_commands():
    global areYouAFK

    show_help()

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
            parts = command.split(", ")

            if len(parts) == 2:
                message, fragment_length = parts
                add_task_to_queue(send_message, message, int(fragment_length), 'm')
            else:
                message = parts[0]
                add_task_to_queue(send_message, message, len(message), 'm')

        elif command.startswith("send file") and state == STATE_CONNECTED:
            command = command.replace("send file (", "").replace(")", "")
            parts = command.split(", ")

            if len(parts) == 2:
                file_name, fragment_length = parts
                add_task_to_queue(send_file, file_name, int(fragment_length),)
            else:
                file_name = parts[0]
                with open(file_name, "rb") as file:
                    content = file.read()
                    total_length = len(content)

                add_task_to_queue(send_file, file_name, total_length)

        elif command == "disconnect" and state == STATE_CONNECTED:
            with lock:
                send_packet(TYPE_FIN)
                change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK

        elif command == "change mode":
            if mode == ORDINARY_MODE:
                change_mode(LOSS_MODE)
                print("Your mode is LOSS_MODE now.")
            else:
                change_mode(ORDINARY_MODE)
                print("Your mode is ORDINARY_MODE now.")
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

message_thread = threading.Thread(target=should_wait_for_fragment, args=())
message_thread.daemon = True
message_thread.start()

# Command handler
handle_commands()