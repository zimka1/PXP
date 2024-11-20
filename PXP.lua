-- Wireshark Lua Dissector for Custom Protocol over UDP

-- Create a new protocol
my_protocol = Proto("PXP", "Peer Exchange Protocol")

-- Define protocol fields
local f_packet_type = ProtoField.uint8("pxp.packet_type", "Packet Type", base.HEX)
local f_packet_id = ProtoField.uint24("pxp.packet_id", "Packet ID", base.DEC)
local f_sequence_number = ProtoField.uint32("pxp.sequence_number", "Sequence Number", base.DEC)
local f_ack_number = ProtoField.uint32("pxp.ack_number", "Acknowledgment Number", base.DEC)
local f_checksum = ProtoField.uint32("pxp.checksum", "Checksum", base.HEX)
local f_payload = ProtoField.bytes("pxp.payload", "Payload")

-- Register fields to protocol
my_protocol.fields = {f_packet_type, f_packet_id, f_sequence_number, f_ack_number, f_checksum, f_payload}

-- Helper function to map packet types to human-readable names
local function get_packet_type_name(packet_type)
    local packet_types = {
        [0x01] = "Message",
        [0x02] = "File",
        [0x03] = "Filename",
        [0x04] = "Window Size",
        [0x05] = "End of Fragments",
        [0x06] = "Check Fragments",
        [0x07] = "ACK",
        [0x08] = "NACK",
        [0x09] = "SYN",
        [0x0A] = "SYN-ACK",
        [0x0B] = "FIN",
        [0x0C] = "FIN-ACK",
        [0x0D] = "Heartbeat",
        [0x0E] = "Heartbeat-ACK"
    }
    return packet_types[packet_type] or "Unknown"
end

-- Main dissector function
function my_protocol.dissector(buffer, pinfo, tree)
    -- Ensure packet length is sufficient
    if buffer:len() < 11 then return end

    -- Update protocol column in Wireshark
    pinfo.cols.protocol = my_protocol.name

    -- Create a subtree for the protocol
    local subtree = tree:add(my_protocol, buffer(), "Peer Exchange Protocol")

    -- Parse fields from the buffer
    local packet_type = buffer(0, 1):uint()
    local packet_id = buffer(1, 3):uint()
    local sequence_number = buffer(4, 4):uint()
    local ack_number = buffer(8, 4):uint()
    local checksum = buffer(12, 4):uint()
    local payload = buffer(16):bytes()

    -- Add parsed fields to the subtree
    subtree:add(f_packet_type, buffer(0, 1)):append_text(" (" .. get_packet_type_name(packet_type) .. ")")
    subtree:add(f_packet_id, buffer(1, 3))
    subtree:add(f_sequence_number, buffer(4, 4))
    subtree:add(f_ack_number, buffer(8, 4))
    subtree:add(f_checksum, buffer(12, 4))
    if payload:len() > 0 then
        subtree:add(f_payload, buffer(16)):append_text(" (" .. payload:len() .. " bytes)")
    end

    -- Highlight subtree for specific packet categories
    if packet_type == 0x01 or packet_type == 0x02 or packet_type == 0x03 then
        subtree:set_text("Data Packet")
    elseif packet_type == 0x07 or packet_type == 0x08 then
        subtree:set_text("Acknowledgment Packet")
    elseif packet_type == 0x09 or packet_type == 0x0A then
        subtree:set_text("Handshake Packet")
    elseif packet_type == 0x0B or packet_type == 0x0C then
        subtree:set_text("Disconnection Packet")
    elseif packet_type == 0x0D or packet_type == 0x0E then
        subtree:set_text("Heartbeat Packet")
    else
        subtree:set_text("Unknown Packet Type")
    end
end

-- Register dissector with UDP ports
local udp_port = DissectorTable.get("udp.port")
udp_port:add(5000, my_protocol)  -- Node 1 port
udp_port:add(5001, my_protocol)  -- Node 2 port
