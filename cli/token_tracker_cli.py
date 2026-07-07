#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
import re
import urllib.request
import ssl
from typing import Dict, List, Any, Optional

class AntigravityProvider:
    """
    Provider implementation for Google Antigravity, querying the local
    gRPC-web endpoints of the running Language Server or CLI.
    """
    
    GET_USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"
    RETRIEVE_USER_QUOTA_SUMMARY_PATH = "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def detect_processes(self) -> List[Dict[str, Any]]:
        """
        Scan /proc (on Linux) or run ps to find running Antigravity processes.
        Returns a list of dicts with 'pid' and 'cmdline'.
        """
        processes = []
        # Try pure Python /proc scanning first (Linux-specific, extremely fast)
        if os.path.exists("/proc"):
            try:
                for name in os.listdir("/proc"):
                    if name.isdigit():
                        pid = int(name)
                        try:
                            with open(f"/proc/{pid}/cmdline", "rb") as f:
                                cmdline_bytes = f.read()
                                # cmdline args are null-separated
                                cmdline = cmdline_bytes.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
                                
                                # Check if it's an antigravity process
                                lower_cmd = cmdline.lower()
                                is_ls = "language-server" in lower_cmd or "language_server" in lower_cmd
                                is_agy = "antigravity" in lower_cmd or "agy" in lower_cmd or "antigravity-cli" in lower_cmd or "antigravity_cli" in lower_cmd
                                
                                if is_ls or is_agy:
                                    processes.append({
                                        "pid": pid,
                                        "cmdline": cmdline
                                    })
                        except (IOError, PermissionError):
                            continue
                if processes:
                    return processes
            except Exception:
                pass

        # Fallback to ps command
        try:
            output = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    pid_str, cmdline = parts
                    pid = int(pid_str)
                    lower_cmd = cmdline.lower()
                    is_ls = "language-server" in lower_cmd or "language_server" in lower_cmd
                    is_agy = "antigravity" in lower_cmd or "agy" in lower_cmd or "antigravity-cli" in lower_cmd or "antigravity_cli" in lower_cmd
                    if is_ls or is_agy:
                        processes.append({
                            "pid": pid,
                            "cmdline": cmdline
                        })
        except Exception:
            pass

        return processes

    def get_listening_ports(self, pid: int) -> List[int]:
        """
        Find TCP listening ports for a given PID.
        Returns a list of port numbers.
        """
        ports = set()
        
        # Method 1: Scan /proc (Linux-only, fast, pure Python)
        if os.path.exists("/proc"):
            try:
                # Find all socket inodes for the process
                fd_dir = f"/proc/{pid}/fd"
                inodes = set()
                for fd in os.listdir(fd_dir):
                    try:
                        link = os.readlink(os.path.join(fd_dir, fd))
                        match = re.match(r"socket:\[(\d+)\]", link)
                        if match:
                            inodes.add(match.group(1))
                    except (IOError, OSError):
                        continue
                
                # Check /proc/net/tcp and tcp6 for matching inodes in state 0A (LISTEN)
                for net_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
                    if not os.path.exists(net_file):
                        continue
                    with open(net_file, "r") as f:
                        lines = f.readlines()
                        # Header: sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
                        for line in lines[1:]:
                            parts = line.split()
                            if len(parts) >= 10:
                                state = parts[3]
                                inode = parts[9]
                                if state == "0A" and inode in inodes:
                                    local_addr = parts[1]
                                    # Format is IP:PORT in hex (e.g. 0100007F:8F25)
                                    if ":" in local_addr:
                                        _, hex_port = local_addr.split(":")
                                        ports.add(int(hex_port, 16))
            except Exception:
                pass
                
        if ports:
            return sorted(list(ports))

        # Method 2: Fallback to lsof
        for lsof_path in ["/usr/bin/lsof", "/usr/sbin/lsof", "lsof"]:
            try:
                output = subprocess.check_output(
                    [lsof_path, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
                    text=True,
                    stderr=subprocess.DEVNULL
                )
                # Output format:
                # COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
                # agy     58027 jason   11u  IPv4 204857      0t0  TCP 127.0.0.1:33267 (LISTEN)
                for line in output.splitlines():
                    match = re.search(r":(\d+)\s+\(LISTEN\)", line)
                    if match:
                        ports.add(int(match.group(1)))
            except Exception:
                continue

        return sorted(list(ports))

    def query_local_endpoint(self, port: int, path: str, body: Dict[str, Any], use_https: bool) -> Optional[Dict[str, Any]]:
        """
        Sends a POST request to a local gRPC-web endpoint.
        """
        scheme = "https" if use_https else "http"
        url = f"{scheme}://127.0.0.1:{port}{path}"
        
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Connect-Protocol-Version", "1")
        
        # Set up SSL context to ignore verification if using HTTPS
        ctx = None
        if use_https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        data = json.dumps(body).encode("utf-8")
        req.data = data
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=self.timeout) as res:
                if res.status == 200:
                    return json.loads(res.read().decode("utf-8"))
        except Exception:
            pass
        return None

    def fetch_data(self) -> Dict[str, Any]:
        """
        Main fetch routine:
        1. Detects processes.
        2. Resolves listening ports.
        3. Queries RetrieveUserQuotaSummary and GetUserStatus.
        4. Merges and formats JSON response.
        """
        processes = self.detect_processes()
        if not processes:
            return {
                "provider": "antigravity",
                "status": "disconnected",
                "error": "Antigravity process not running"
            }

        # Find ports for detected processes
        ports_with_pids = []
        for p in processes:
            pid = p["pid"]
            ports = self.get_listening_ports(pid)
            for port in ports:
                ports_with_pids.append((port, pid))

        if not ports_with_pids:
            return {
                "provider": "antigravity",
                "status": "disconnected",
                "error": "No listening ports found for Antigravity"
            }

        # Query endpoints on found ports (try HTTPS first, then HTTP)
        quota_summary = None
        user_status = None
        
        for port, pid in ports_with_pids:
            for use_https in [True, False]:
                # Try to fetch Quota Summary
                q_res = self.query_local_endpoint(
                    port, 
                    self.RETRIEVE_USER_QUOTA_SUMMARY_PATH, 
                    {"forceRefresh": True}, 
                    use_https
                )
                if q_res:
                    quota_summary = q_res
                    
                # Try to fetch User Status
                u_res = self.query_local_endpoint(
                    port, 
                    self.GET_USER_STATUS_PATH, 
                    {}, 
                    use_https
                )
                if u_res:
                    user_status = u_res
                    
                if quota_summary or user_status:
                    break
            if quota_summary or user_status:
                break

        if not quota_summary and not user_status:
            return {
                "provider": "antigravity",
                "status": "disconnected",
                "error": "Failed to retrieve quota or status from local server"
            }

        # Format and merge output
        result = {
            "provider": "antigravity",
            "status": "connected",
            "email": None,
            "plan": None,
            "groups": []
        }

        # Add details from user_status
        if user_status and "userStatus" in user_status:
            status_info = user_status["userStatus"]
            result["email"] = status_info.get("email")
            
            # Prefer userTier.name, fallback to planStatus.planInfo
            tier = status_info.get("userTier", {})
            plan = status_info.get("planStatus", {}).get("planInfo", {})
            result["plan"] = tier.get("name") or plan.get("displayName") or plan.get("planName")

        # Add groups and buckets from quota_summary
        summary_payload = {}
        if quota_summary:
            summary_payload = quota_summary.get("response") or quota_summary.get("summary") or {}
            
        if summary_payload and "groups" in summary_payload:
            for g in summary_payload["groups"]:
                group_data = {
                    "name": g.get("displayName", "Quota"),
                    "description": g.get("description"),
                    "buckets": []
                }
                for b in g.get("buckets", []):
                    if b.get("disabled", False):
                        continue
                    group_data["buckets"].append({
                        "id": b.get("bucketId"),
                        "name": b.get("displayName"),
                        "description": b.get("description"),
                        "remaining_fraction": b.get("remainingFraction"),
                        "reset_time": b.get("resetTime")
                    })
                result["groups"].append(group_data)
        elif user_status and "userStatus" in user_status:
            # Fallback to model configs if full quota summary is unavailable
            status_info = user_status["userStatus"]
            model_configs = status_info.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
            if model_configs:
                fallback_group = {
                    "name": "Model Quotas",
                    "description": "Rate limits per model",
                    "buckets": []
                }
                for config in model_configs:
                    quota = config.get("quotaInfo")
                    if quota:
                        fallback_group["buckets"].append({
                            "id": config.get("modelOrAlias", {}).get("model"),
                            "name": config.get("label"),
                            "description": None,
                            "remaining_fraction": quota.get("remainingFraction"),
                            "reset_time": quota.get("resetTime")
                        })
                result["groups"].append(fallback_group)

        return result

def main():
    parser = argparse.ArgumentParser(description="Token Tracker CLI Helper")
    parser.add_argument(
        "--provider", 
        default="antigravity", 
        choices=["antigravity"],
        help="Specify the AI provider (default: antigravity)"
    )
    args = parser.parse_args()

    if args.provider == "antigravity":
        provider = AntigravityProvider()
        data = provider.fetch_data()
        print(json.dumps(data, indent=2))
        if data.get("status") == "disconnected":
            sys.exit(1)
        sys.exit(0)

if __name__ == "__main__":
    main()
