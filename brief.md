# Project Brief: Operation ColdStart – An Immersive OT/ICS CTF Simulation

Set in an abandoned, decaying industrial facility cut off from the outside world, 
Operation ColdStart is a progressive Operational Technology (OT) and Industrial Control System (ICS) 
Capture The Flag challenge where the player’s survival hinges on methodically reviving dormant machinery.
Drawing inspiration from factory automation games, the environment immerses players in an interactive 
manufacturing plant where physical progression is tethered directly to industrial network exploitation. 
Upon awakening, the player is faced with non-responsive conveyor belts, darkened human-machine interfaces (HMIs),
disconnected programmable logic controllers (PLCs), and cold power generation units. 
To escape or restore life support, the challenger must step into the dual role of automation engineer 
and offensive security specialist—diagnosing industrial network topologies, reverse-engineering ladder logic,
injecting malicious setpoints, and fuzzing industrial protocol endpoints to bring individual assembly stages back online, 
revealing cryptographic flags at each milestone.

The challenge progresses through distinct, isolated operational zones, each mapped to a critical protocol layer and vulnerability class:
## Zone 1: Power Restoration & Conveyor Revival (Modbus TCP)

Narrative: The primary sorting floor is lifeless; the motor control centers are locked.

Vulnerability & Mechanics: An insecure Modbus TCP link controls relay coils and conveyor variable-frequency 
drives (VFDs). Players must perform unauthenticated register enumeration, e
xecute Modbus frame injection to force coil actuation, or replay control traffic to spin up the conveyors, 
dumping the first flag from a simulated diagnostic register.

## Zone 2: HVAC & Life Support Stabilization (BACnet/IP)

Narrative: Hazardous gases and stale air threaten the facility; 
the atmospheric scrubbers and dampers are in an alert state.

Vulnerability & Mechanics: The building management system uses BACnet/IP.
Players must discover device IDs via Who-Is broadcasts, perform unauthorized property writes
(WriteProperty) on air damper setpoints, or fuzz proprietary BACnet object identifiers to trigger an 
unhandled crash state that bypasses ventilation interlocks, capturing the environmental flag.

## Zone 3: Assembly & Telemetry Aggregation (OPC-UA)

Narrative: Automated pick-and-place robotic arms are out of sync with sensor telemetry, halting the central assembly pipeline.

Vulnerability & Mechanics: The plant relies on an OPC-UA endpoint running in an insecure configuration 
(None:None security policy or misconfigured x509 certificate validation). Players exploit missing access 
controls to browse sensitive address-space nodes, alter production variables, 
or manipulate subscribed telemetry streams to force the machines into calibration mode.

Zone 4: Reactor Safeguards & Main Turbine Synchronization (Siemens S7comm / S7comm-Plus)

Narrative: The high-voltage turbine powering the egress blast doors is held hostage by a
compromised Siemens S7 PLC running legacy firmware.

Vulnerability & Mechanics: Players must inspect S7 communication traffic, 
craft custom PDU packets to manipulate DB (Data Block) memory structures without authentication, 
or fuzz proprietary S7 commands to induce a PLC Denial of Service / fault state (OB80 cycle time violation
or cold restart), forcing open the facility’s failsafe lockdown mechanisms to retrieve the final root flag.




