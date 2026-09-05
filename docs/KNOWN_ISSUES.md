# Known Issues

## NET-001: NX target unreachable over wired Ethernet

- Status: BLOCKED
- Symptom: SSH to `10.33.154.71` times out; ICMP probe fails.
- Reproduction: From the Windows development host, run `Test-NetConnection 10.33.154.71 -Port 22`.
- Evidence: USB GbE interface has a 1 Gbps physical link. With authorized host address `10.33.154.70/24`, Windows has an active direct route to `10.33.154.0/24` but learns no ARP entry for `10.33.154.71`; three ICMP probes return `Destination host unreachable`.
- Suspected cause: The target is not currently using the documented IP, the cable is connected to a different Jetson Ethernet interface, or its network interface is down.
- Excluded: Local Ethernet physical-link loss (interface reports Up at 1 Gbps).
- Attempted: Read-only TCP/22 and ICMP probes.
- Current conclusion: User-approved host-network alignment or a Jetson-console check is required before SSH audit.
- Next step: On the Jetson local console, check `ip -br addr` and `ip link`; confirm the connected interface and IPv4 prefix before another host-side configuration change.
