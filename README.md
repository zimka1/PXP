# 📡 PXP – Peer Exchange Protocol over UDP

**Author:** Aliaksei Zimnitski  
**Institution:** FIIT STU  
**Date:** November 25, 2024  

## 🚀 Overview

The **Peer Exchange Protocol (PXP)** is a custom-designed communication protocol built over **UDP**, enabling **reliable**, **fragmented**, and **acknowledged** data exchange between peers. It supports:

- Message and file transmission with fragmentation.
- Dynamic window sizing (Selective Repeat ARQ).
- Simulated packet loss.
- Heartbeat mechanism for AFK detection.
- Multi-threaded operation with task queuing.

---

## 🧠 Features

- 📦 **Custom Packet Structure:** Includes flag, ID, sequence number, window size, checksum, and payload.
- 🔄 **Reliable Transmission:** Implements **Selective Repeat** protocol for efficient re-transmission.
- 📁 **File & Message Support:** Transfer files or plain text with optional fragmentation.
- 🛠 **Dynamic Window Control:** Adaptive alpha-beta window sizing based on successful/failed transmissions.
- ❤️ **Heartbeat System:** Detects lost connections and ensures liveness.
- 🔁 **Resilient Mode:** Switch between **ORDINARY** and **LOSS** modes to test with random loss/damage.
- 📂 **Configurable Save Directory:** Default is `saved_messages`, but can be changed during runtime.
- 🔒 **Thread-Safe Queuing:** Uses locks and threads to handle tasks concurrently.

---

## 🛠 Installation & Running

1. Ensure you have **Python 3.x** installed.
2. Run the script:
   ```bash
   python3 main.py
   ```
3. Provide:
   - Local port to listen on
   - Remote peer IP address
   - Remote peer port

---

## 💬 Supported Commands

Use the following commands during runtime:

| Command | Description |
|--------|-------------|
| `help` | Show available commands |
| `connect` | Initiate connection (3-way handshake) |
| `disconnect` | Graceful connection termination |
| `change mode` | Toggle between `ORDINARY` and `LOSS` mode |
| `send message (<message>, <fragment_size>)` | Send a message in fragments |
| `send message (<message>)` | Send message without fragmentation |
| `send file (<file_path>, <fragment_size>)` | Send file in fragments |
| `send file (<file_path>)` | Send file without fragmentation |
| `change repo (<path>)` | Change save location for received files/messages |

> 🧪 **Note:** Commands only work when the state is `CONNECTED`, except `help` and `connect`.

---

## 📦 Packet Structure

Each PXP packet includes:

- **Type (1 byte)** – e.g., SYN, ACK, FILE, etc.
- **Packet ID (3 bytes)** – unique per transmission.
- **Sequence Number (4 bytes)** – for ordering.
- **Window Size (4 bytes)** – used for SR-ARQ logic.
- **Checksum (4 bytes)** – CRC32 integrity check.
- **Payload** – actual data (message, file chunk, etc.)

---

## 🔐 Connection Lifecycle

PXP uses a custom **3-way handshake** and **4-step termination**:

### Handshake

1. `SYN` →  
2. `SYN-ACK` ←  
3. `ACK` →

### Termination

1. `FIN` →  
2. `FIN-ACK` ←  
3. `FIN` ←  
4. `ACK` →

---

## 📊 Flow Control with Selective Repeat

- **Window size** is adaptive.
- If all fragments are received: window increases.
- If NACK received: retransmit missing fragments and shrink window.

---

## 🧪 Testing & Validation

- All packet types tested via **Wireshark**.
- Simulations run in both **ORDINARY** and **LOSS** modes.
- A 2MB file transfers in ~17s at 1450-byte fragment size.
- Handles packet corruption, loss, retransmission, and reordering.

---

## 📁 Output & File Saving

- Files are saved to `saved_messages/` by default.
- Naming is auto-handled to avoid overwriting.
- Messages are printed directly in the terminal.

---

## 📚 Documentation

For an in-depth explanation of the architecture, packet types, state transitions, and Wireshark test cases, see the included [📄 documentation.pdf](./documentation.pdf).

---

## 🧠 Future Enhancements

- Add GUI interface for easier use.
- Support for TCP fallback.
- Multi-peer topology support.
- Encryption and authentication.
