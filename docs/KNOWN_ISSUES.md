# Known Issues

## NET-001: NX target unreachable over wired Ethernet

- Status: BLOCKED
- Symptom: SSH to `10.33.154.71` times out; ICMP probe fails.
- Reproduction: From the Windows development host, run `Test-NetConnection 10.33.154.71 -Port 22`.
- Evidence: USB GbE interface has 1 Gbps link and `192.168.0.200/24`; it has no route or ARP entry for the target IP.
- Suspected cause: Host and target use different IPv4 subnets, or the target is not currently using the documented IP.
- Excluded: Local Ethernet physical-link loss (interface reports Up at 1 Gbps).
- Attempted: Read-only TCP/22 and ICMP probes.
- Current conclusion: User-approved host-network alignment or a Jetson-console check is required before SSH audit.
- Next step: Confirm the Jetson Ethernet IPv4 address/prefix locally, then configure the host adapter accordingly.
