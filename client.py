import socket
import threading
import time
from queue import Queue
from dataclasses import dataclass, field
import os
import random
from typing import List
import math

@dataclass
class TransferredData:
    filename: str
    type: int
    arrayOfFragments: List = field(default_factory=list)

@dataclass
class ParsedPacket:
    packet_flag: int = 0  # Packet type
    packet_id: int = 0  # Unique packet identifier
    sequence_number: int = 0  # Current fragment number
    acknowledgment_number: int = 0 # Window size
    checksum: int = 0  # Checksum for error detection
    payload: bytes = field(default_factory=lambda: bytes())  # Payload (message or data)

blue_text = "\033[94m"
reset_text = "\033[0m"
red_text = "\033[91m"
yellow_text = "\033[93m"
green_text = "\033[92m"

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
TYPE_FILE = 0x02  # Packet type: DATA (file or data transmission)
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
save_repository_path = "saved_messages"

heartbeat_interval = 5
heartbeat_interval_to_ans = 2
max_missed_heartbeats = 3
heartbeat_missed = 0
heartbeat_received = False
areYouAFK = 1

start_sending = 0
end_sending = 0
sent_packets = []
missed_packets = []
fragment_come = False
time_fragment_come = time.time()
dont_should_wait = True

packet_ID = -1
last_fragment_packet = ParsedPacket()
canISendFragments = True
allReceived = True
fragments = []
total_data = []
max_value_of_fragment = 1450

window_size = 0
max_window_size = 0
min_window_size = 6
alpha = 0
beta = 0

# Mutex for preventing simultaneous execution
lock = threading.Lock()

# Message queue for sending messages
message_queue = Queue()


def change_state(new_state):
    global state
    state = new_state

def change_mode(new_mode):
    global mode
    mode = new_mode

# Creates the packet with specified parameters and encodes it to bytes
def create_packet(packet_flag, packet_id, sequence_number, acknowledgment_number, checksum, payload):
    packet = packet_flag.to_bytes(1, 'big')  # Packet type (1 byte)
    packet += packet_id.to_bytes(3, 'big')  # Packet ID (3 bytes)
    packet += sequence_number.to_bytes(4, 'big')  # Sequence number (4 byte)
    packet += acknowledgment_number.to_bytes(4, 'big')  # Acknowledgment number (4 bytes)
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
    packet_id = int.from_bytes(packet[1:4], 'big')  # Packet ID (3 bytes)
    sequence_number = int.from_bytes(packet[4:8], 'big')  # Sequence number (4 byte)
    acknowledgment_number = int.from_bytes(packet[8:12], 'big') # Acknowledgment number (4 bytes)
    checksum = int.from_bytes(packet[12:16], 'big')  # Checksum (4 bytes)
    payload = packet[16:] # Payload (decoded as UTF-8)

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
{yellow_text}9. {blue_text}change repo (<path>){reset_text} - Change the repository for saving.(Initial path - "saved_messages"){reset_text}
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
                print(f"{green_text}Handshake complete.{reset_text}")
                change_state(STATE_CONNECTED)  # Move to CONNECTED state


# Sends SYN and waits for SYN-ACK to complete the handshake
def continue_handshake():
    with lock:
        if state == STATE_WAIT_SYN_ACK:
            send_packet(TYPE_ACK)  # Send ACK
            print(f"{green_text}Handshake complete.{reset_text}")
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
                print(f"{red_text}Connection terminated.{reset_text}")
                change_state(STATE_DISCONNECTED)  # Move back to DISCONNECTED state


# Completes the termination by sending the final ACK
def continue_termination():
    with lock:
        if state == STATE_WAIT_FIN_ACK:
            data, addr = sock.recvfrom(1024)
            packet = parse_packet(data)
            if packet.packet_flag == TYPE_FIN:
                send_packet(TYPE_ACK)  # Send final ACK
                print(f"{red_text}Connection terminated.{reset_text}")
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
            print(f"{red_text}Connection lost. No response from the partner.{reset_text}")
            heartbeat_missed = 0
            change_state(STATE_DISCONNECTED)
            break


def calculate_crc32(data: bytes) -> int:
    # Initialize CRC and polynomial for 32-bit
    crc = 0xFFFFFFFF  # Initialization of the 32-bit CRC value
    polynomial = 0x04C11DB7  # Standard polynomial for CRC32

    # Process each byte in the data
    for byte in data:
        crc ^= byte << 24  # XOR with each byte, shifted by 24 bits
        for _ in range(8):
            if crc & 0x80000000:  # If the most significant bit (32nd) is 1
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF  # Ensure 32-bit value

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


def send_again(total_length, file_name=""):
    global allReceived, missed_packets, canISendFragments
    time.sleep(0.5)
    for sequence_number_of_missed_packet in missed_packets:
        for sent_packet in sent_packets:
            parsed_sent_packet = parse_packet(sent_packet)
            # print(parsed_sent_packet)
            if parsed_sent_packet.sequence_number == sequence_number_of_missed_packet:
                print(f"{red_text}Send again:{reset_text}")
                if file_name:
                    print(f"{blue_text}File name:{reset_text} {file_name}, {blue_text}Total length:{reset_text} {total_length}, {blue_text}Number of sent fragments:{reset_text} {parsed_sent_packet.sequence_number} {blue_text}Fragment length:{reset_text} {len(parsed_sent_packet.payload)}")
                else:
                    print(f"{blue_text}Total length:{reset_text} {total_length}, {blue_text}Number of sent fragments:{reset_text} {parsed_sent_packet.sequence_number} {blue_text}Fragment length:{reset_text} {len(parsed_sent_packet.payload)}")
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

def send_file(file_path, fragment_length):
    global packet_ID, state, canISendFragments, allReceived, missed_packets, sent_packets

    packet_ID += 1

    sequence_number = -1
    window_number = 0

    with open(file_path, "rb") as file:
        content = file.read()
        total_length = len(content)

    file_name = os.path.basename(file_path)

    send_message(file_name, len(file_name) if total_length == fragment_length else fragment_length, 'n')

    set_window_settings(total_length, fragment_length)

    with open(file_path, "rb") as file:
        data = file.read(fragment_length)
        while True:
            if allReceived:
                if not data:
                    break

                crc = calculate_crc32(data)
                sequence_number += 1
                window_number += 1

                if window_number == 1:
                    how_much_left = max(math.ceil((total_length - sequence_number * fragment_length) / fragment_length), 1)
                    acknowledgment_number = min(window_size, how_much_left)
                    send_packet(TYPE_MAKE_MONITOR, packet_ID, 0, acknowledgment_number)

                print(f"{blue_text}File name:{reset_text} {file_name}, {blue_text}Total length:{reset_text} {total_length}, {blue_text}Number of sent fragments:{reset_text} {sequence_number} {blue_text}Fragment length:{reset_text} {len(data)}, {blue_text}Current size of window: {reset_text}{window_size}, {blue_text}Fragment number in the window: {reset_text}{window_number}")

                if not should_drop_or_damage_packet(0.1):
                    send_packet(TYPE_FILE, packet_ID, sequence_number,0, crc if not should_drop_or_damage_packet(0.1) else damage_packet(crc), data)
                else:
                    print(f"{red_text}Attention!!!{reset_text} Fragment {sequence_number} dropped!{reset_text}")

                packet = create_packet(TYPE_FILE, packet_ID, sequence_number, 0, crc, data)
                sent_packets.append(packet)

                data = file.read(fragment_length)

                if window_number == window_size or (not data and window_number != 0):
                    canISendFragments = False
                    print(f"{red_text}Wait for ack{reset_text}")
                    wait_for_ack()
                    if state == STATE_DISCONNECTED:
                        return
                    window_number = 0
                    if allReceived:
                        on_successful_ack()
                    else:
                        on_packet_loss()
            else:
                send_again(total_length, file_name)
                print(f"{red_text}Wait for ack{reset_text}")
                wait_for_ack()
                if state == STATE_DISCONNECTED:
                    print(f"{red_text}The transfer was unsuccessful.{reset_text}")
                    return


    send_packet(TYPE_FIN_FRAG, packet_ID, 0, window_number)

    sent_packets = []

    print(f"{green_text}Partner has all fragments!{reset_text}")


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

            if window_number == 1:
                how_much_left = max(math.ceil((total_length - sequence_number * fragment_length) / fragment_length), 1)
                acknowledgment_number = min(window_size, how_much_left)
                send_packet(TYPE_MAKE_MONITOR, packet_ID, 0, acknowledgment_number)

            print(f"{blue_text}Total length:{reset_text} {total_length}, {blue_text}Number of sent fragments:{reset_text} {sequence_number} {blue_text}, Fragment length:{reset_text} {len(fragment)}, {blue_text}Current size of window: {reset_text}{window_size}, {blue_text}Fragment number in the window: {reset_text}{window_number}")

            if not should_drop_or_damage_packet(0.1):
                send_packet(TYPE_FILENAME if flag == 'n' else TYPE_MESSAGE, packet_ID, sequence_number, 0, crc if not should_drop_or_damage_packet(0.1) else damage_packet(crc), fragment)
            else:
                print(f"{red_text}Attention!!!{reset_text} Fragment {sequence_number} dropped!{reset_text}")
            packet = create_packet(TYPE_FILENAME if flag == 'n' else TYPE_MESSAGE, packet_ID, sequence_number, 0, crc, fragment)
            sent_packets.append(packet)

            if window_number == window_size or (position + fragment_length >= total_length and window_number != 0):
                canISendFragments = False
                print(f"{red_text}Wait for ack{reset_text}")
                wait_for_ack()
                if state == STATE_DISCONNECTED:
                    return
                window_number = 0
                if allReceived:
                    on_successful_ack()
                else:
                    on_packet_loss()
        else:

            send_again(total_length)
            print(f"{red_text}Wait for ack{reset_text}")
            wait_for_ack()
            if state == STATE_DISCONNECTED:
                print(f"{red_text}The transfer was unsuccessful.{reset_text}")
                return

    send_packet(TYPE_FIN_FRAG, packet_ID, 0, window_number)

    sent_packets = []

    if flag != 'n':
        print(f"{green_text}Partner has all fragments!{reset_text}")
    else:
        print(f"{green_text}Partner has all fragments of filename!{reset_text}")


def check_fragments(frags_array):
    for fragment in frags_array:
        if not fragment:
            return False
    return True


def checkIfSomethingIsWrong(packet):
    global fragment_come, start_sending

    if packet.packet_id + 1 > len(fragments):
        fragments.append(TransferredData("", 0, []))
        total_data.append(b"")

    if not start_sending:
        start_sending = time.time()

    if packet.packet_flag == TYPE_MAKE_MONITOR:
        fragments[packet.packet_id].arrayOfFragments.extend([None] * packet.acknowledgment_number)
        return

    if packet.packet_flag == TYPE_FILENAME or packet.packet_flag == TYPE_MESSAGE or packet.packet_flag == TYPE_FILE:
        calculated_crc = calculate_crc32(packet.payload)
        fragments[packet.packet_id].type = packet.packet_flag

        if calculated_crc == packet.checksum:
            print(f"{blue_text}Number of fragment: {reset_text}{packet.sequence_number}, {blue_text}Status: {green_text}successful")
            fragments[packet.packet_id].arrayOfFragments[packet.sequence_number] = packet.payload
        else:
            print(f"{blue_text}Number of fragment: {reset_text}{packet.sequence_number}, {blue_text}Status: {red_text}unsuccessful")

    if packet.packet_flag == TYPE_CHECK:
        if check_fragments(fragments[packet.packet_id].arrayOfFragments):
            send_packet(TYPE_ACK)
        else:
            missed = ""
            for i,fragment in enumerate(fragments[packet.packet_id].arrayOfFragments):
                if not fragment:
                    missed += str(i) + " "
            send_packet(TYPE_NACK, packet.packet_id, 0, 0, packet.checksum, missed.encode('utf-8'))


def should_wait_for_fragment():
    global last_fragment_packet, time_fragment_come, fragment_come
    while True:
        if fragment_come:
            current_time = time.time()
            while current_time - time_fragment_come < 1:
                if not fragment_come:
                    break
                current_time = time.time()
            if fragment_come:
                packet = ParsedPacket(TYPE_CHECK, last_fragment_packet.packet_id, 0, 0, 0, "0".encode('utf-8'))
                checkIfSomethingIsWrong(packet)
                fragment_come = False



def check_file_exists(file_path):
    # Check if file exists at the given path
    return os.path.isfile(file_path)


def save_data(packet):
    global fragment_come, end_sending, start_sending

    total_data[packet.packet_id] += b''.join(frag for frag in fragments[packet.packet_id].arrayOfFragments)

    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id].filename = total_data[packet.packet_id].decode('utf-8')
    if fragments[packet.packet_id].type == TYPE_MESSAGE:
        print(f"{blue_text}You got text message:{reset_text}")
        print(f"{total_data[packet.packet_id].decode('utf-8')}")

    elif fragments[packet.packet_id].type == TYPE_FILE:
        # Ensure the directory 'saved messages' exists
        output_directory = save_repository_path
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        # Generate unique filename for received file
        filename = ""
        is_filename_found = False
        file_number = 0
        name, filetype = fragments[packet.packet_id].filename.split('.')

        while not is_filename_found:
            if not file_number:
                cur_filename = os.path.join(output_directory, "received_" + name + '.' + filetype)
            else:
                cur_filename = os.path.join(output_directory, "received_" + name + "_" + str(file_number) + '.' + filetype)
            if not check_file_exists(cur_filename):
                filename = cur_filename
                is_filename_found = True
            file_number += 1

        # Save total message content to the determined filename
        with open(filename, "ab") as file:
            file.write(total_data[packet.packet_id])

        end_sending = time.time()

        print(f"{green_text}The transfer was successful. {blue_text}Duration of the transfer: {reset_text}{end_sending - start_sending}, {blue_text}Total length: {reset_text}{len(total_data[packet.packet_id])}, {blue_text}Path: {reset_text}{filename}")
        start_sending = 0
    # Reset total message and fragments after saving
    total_data[packet.packet_id] = b""
    if fragments[packet.packet_id].type == TYPE_FILENAME:
        fragments[packet.packet_id] = TransferredData(fragments[packet.packet_id].filename, TYPE_FILE, [])


# Receives packets and handles the protocol logic for various packet types
def receive_packet():
    global heartbeat_received, allReceived, canISendFragments, areYouAFK, last_fragment_packet, time_fragment_come, fragment_come, missed_packets

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

        if (packet.packet_flag == TYPE_FILE or packet.packet_flag == TYPE_MESSAGE
                or packet.packet_flag == TYPE_FILENAME or packet.packet_flag == TYPE_MAKE_MONITOR):
            last_fragment_packet = packet
            fragment_come = True
            time_fragment_come = time.time()
            checkIfSomethingIsWrong(packet)
            continue

        if packet.packet_flag == TYPE_FIN_FRAG:
            fragment_come = False
            save_data(packet)


def handle_commands():
    global areYouAFK, save_repository_path

    show_help()

    while True:
        command = input().strip().lower()

        if command == "connect" and state == STATE_DISCONNECTED:
            with lock:  # Using lock
                send_packet(TYPE_SYN)
                change_state(STATE_WAIT_SYN_ACK)  # Transition to the state waiting for SYN-ACK
            time.sleep(2)
            if state == STATE_WAIT_SYN_ACK:
                print(f"{red_text}Connection error.{reset_text}")
                change_state(STATE_DISCONNECTED)

        elif command.startswith("send message") and state == STATE_CONNECTED:
            command = command.replace("send message (", "").replace(")", "")
            parts = command.split(", ")

            if len(parts) == 2:
                message, fragment_length = parts
                if 0 < int(fragment_length) > max_value_of_fragment  or int(fragment_length) <= 0:
                    print(f"{red_text}[Error]{reset_text} Invalid size: the fragment must be greater than 0 and cannot exceed 1450 bytes.")
                    continue
                add_task_to_queue(send_message, message, int(fragment_length), 'm')
            else:
                message = parts[0]
                add_task_to_queue(send_message, message, max_value_of_fragment, 'm')

        elif command.startswith("send file") and state == STATE_CONNECTED:
            command = command.replace("send file (", "").replace(")", "")
            parts = command.split(", ")

            file_path = parts[0]
            if not os.path.exists(file_path):
                print(f"{red_text}[Error]{reset_text} File doesn't exist.")
                continue

            if len(parts) == 2:
                fragment_length = parts[1]
                if int(fragment_length) > max_value_of_fragment or int(fragment_length) <= 0:
                    print(f"{red_text}[Error]{reset_text} Invalid size: the fragment must be greater than 0 and cannot exceed 1450 bytes.")
                    continue
                add_task_to_queue(send_file, file_path, int(fragment_length))
            else:
                file_path = parts[0]
                add_task_to_queue(send_file, file_path, max_value_of_fragment)

        elif command == "disconnect" and state == STATE_CONNECTED:
            with lock:
                send_packet(TYPE_FIN)
                change_state(STATE_WAIT_FIN_ACK)  # Transition to the state waiting for FIN-ACK

        elif command == "change mode":
            if mode == ORDINARY_MODE:
                change_mode(LOSS_MODE)
                print(f"Your mode is {blue_text}LOSS_MODE{reset_text} now.")
            else:
                change_mode(ORDINARY_MODE)
                print(f"Your mode is {blue_text}ORDINARY_MODE{reset_text} now.")
            continue

        elif command.startswith("change repo") and state == STATE_CONNECTED:
            path = command.replace("change repo (", "").replace(")", "")
            print (f"The save repository has been updated to '{path}'")
            save_repository_path = path
            continue
        else:
            print(f"{red_text}Invalid command or inappropriate state.{reset_text} Type {blue_text}'help'{reset_text} for the list of available commands.")
            continue


        areYouAFK = 0


def add_task_to_queue(task, *args):
    message_queue.put((task, args))


def process_task_queue():
    while True:
        if not message_queue.empty():
            if state == STATE_CONNECTED:
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
receive_thread = threading.Thread(target=receive_packet, args=())
receive_thread.daemon = True
receive_thread.start()

# Thread for Heartbeat
heartbeat_thread = threading.Thread(target=wait_for_heartbeat, args=())
heartbeat_thread.daemon = True
heartbeat_thread.start()

# Thread for processing message queue
message_thread = threading.Thread(target=process_task_queue, args=())
message_thread.daemon = True
message_thread.start()

message_thread = threading.Thread(target=should_wait_for_fragment, args=())
message_thread.daemon = True
message_thread.start()

# Command handler
handle_commands()