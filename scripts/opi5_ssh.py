"""SSH helper for Orange Pi 5 via Tailscale."""
import paramiko
import sys

HOST = "100.119.45.114"
USER = "orangepi"
PASS = "orangepi"


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=15)
    return client


def run(cmd, timeout=60):
    client = connect()
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    return code, out, err


def sftp_put(local_path, remote_path):
    client = connect()
    sftp = client.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    client.close()


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "echo CONNECTED; whoami; uname -a; pwd"
    code, out, err = run(cmd)
    print(f"[exit={code}]")
    if out:
        print(out)
    if err:
        print(f"[stderr]\n{err}", file=sys.stderr)
