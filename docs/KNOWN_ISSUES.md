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
- Current conclusion: The documented IPv4 target is absent from the direct link, but an IPv6 link-local SSH endpoint is reachable at `fe80::6e31:329f:3bf6:41ad%9` (MAC `48-B0-2D-E9-F0-B4`). Its identity is pending an interactive login.
- Next step: Locally authenticate to the IPv6 endpoint, run `hostname; ip -br addr`, and use the result to correct the target-network record.
