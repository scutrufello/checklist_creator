import glob
import logging
import os
import subprocess
import time

import httpx

logger = logging.getLogger(__name__)


class VPNManager:
    def __init__(self, config: dict):
        vpn_cfg = config["vpn"]
        self.auth_file = os.path.abspath(vpn_cfg["auth_file"])
        self.config_dir = os.path.abspath(vpn_cfg["config_dir"])
        self.rotate_every = vpn_cfg.get("rotate_every", 25)
        self.connect_timeout = vpn_cfg.get("connect_timeout", 30)
        self.disconnect_kill_timeout = vpn_cfg.get("disconnect_kill_timeout", 45)
        self.log_public_ip_every_n_requests = vpn_cfg.get("log_public_ip_every_n_requests", 25)
        self.process = None
        self.current_index = 0
        self.request_count = 0
        self.original_ip = None
        self.current_public_ip: str | None = None
        self.current_endpoint_name: str | None = None
        self.configs = sorted(glob.glob(os.path.join(self.config_dir, "*.ovpn")))
        self._enabled_config = vpn_cfg.get("enabled", True)

        if not self.configs:
            logger.warning("No .ovpn files found in %s — VPN disabled", self.config_dir)

    @property
    def enabled(self):
        return self._enabled_config and len(self.configs) > 0

    def get_public_ip(self) -> str | None:
        for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
            try:
                resp = httpx.get(url, timeout=10)
                if resp.status_code == 200:
                    return resp.text.strip()
            except Exception:
                continue
        return None

    def connect(self):
        if not self.enabled:
            logger.info("VPN disabled (no configs). Running without VPN.")
            return

        if self.original_ip is None:
            self.original_ip = self.get_public_ip()
            logger.info("Original IP: %s", self.original_ip)

        config_file = self.configs[self.current_index]
        self.current_endpoint_name = os.path.basename(config_file)
        logger.info(
            "Connecting VPN endpoint [%d/%d]: %s",
            self.current_index + 1,
            len(self.configs),
            self.current_endpoint_name,
        )

        self.process = subprocess.Popen(
            [
                "sudo", "openvpn",
                "--config", config_file,
                "--auth-user-pass", self.auth_file,
                "--daemon",
                "--log", "/tmp/openvpn.log",
                "--writepid", "/tmp/openvpn.pid",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not self._wait_for_tun_up():
            raise RuntimeError("VPN tun interface did not come up within timeout")

        new_ip = self.get_public_ip()
        self.current_public_ip = new_ip
        if new_ip and new_ip != self.original_ip:
            logger.info(
                "VPN up | public_ip=%s | endpoint=%s | original_ip_was=%s",
                new_ip,
                self.current_endpoint_name,
                self.original_ip,
            )
        else:
            logger.warning(
                "VPN may not be routing traffic | public_ip=%s | endpoint=%s | original_ip_was=%s",
                new_ip,
                self.current_endpoint_name,
                self.original_ip,
            )

        self.request_count = 0

    def disconnect(self):
        if not self.enabled:
            return
        logger.info("Disconnecting VPN...")
        for label, args in (
            ("SIGTERM", ["sudo", "-n", "killall", "openvpn"]),
            ("SIGKILL", ["sudo", "-n", "killall", "-9", "openvpn"]),
        ):
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=self.disconnect_kill_timeout)
                if r.returncode != 0 and r.stderr:
                    logger.debug("killall (%s): %s", label, r.stderr.strip()[:200])
            except subprocess.TimeoutExpired:
                logger.warning(
                    "killall openvpn timed out after %ds (%s); tunnel may still be up",
                    self.disconnect_kill_timeout,
                    label,
                )
            except FileNotFoundError:
                logger.warning("sudo/killall not found; cannot tear down OpenVPN cleanly")
                break
            except Exception as e:
                logger.warning("killall openvpn failed (%s): %s", label, e)
            self._wait_for_tun_down()
            up = subprocess.run(["ip", "link", "show", "tun0"], capture_output=True)
            if up.returncode != 0:
                break
        else:
            logger.warning("tun0 still present after disconnect; next connect() may fail")

        self.process = None
        logger.info("VPN disconnected.")

    def rotate(self):
        if not self.enabled:
            return
        prev_ep = self.current_endpoint_name
        prev_ip = self.current_public_ip
        logger.info(
            "[VPN ROTATE] leaving endpoint=%s public_ip=%s -> switching (rotate_every=%d)",
            prev_ep,
            prev_ip,
            self.rotate_every,
        )
        try:
            self.disconnect()
            time.sleep(3)
            self.current_index = (self.current_index + 1) % len(self.configs)
            self.connect()
        except Exception:
            logger.exception(
                "[VPN ROTATE] disconnect/reconnect failed (tried endpoint=%s) — "
                "continuing without aborting scrape",
                os.path.basename(self.configs[self.current_index]),
            )

    def tick(self):
        """Call after each successful TCDB page fetch. Auto-rotates when threshold is reached."""
        self.request_count += 1
        n = self.log_public_ip_every_n_requests
        if self.enabled and n and self.request_count % n == 0:
            ip = self.get_public_ip()
            logger.info(
                "[VPN STATUS] successful_pages=%d | endpoint=%s | public_ip=%s (periodic check)",
                self.request_count,
                self.current_endpoint_name,
                ip,
            )
        if self.enabled and self.request_count >= self.rotate_every:
            logger.info(
                "Rotation threshold (%d successful pages) reached on endpoint=%s",
                self.rotate_every,
                self.current_endpoint_name,
            )
            self.rotate()

    def _wait_for_tun_up(self) -> bool:
        deadline = time.time() + self.connect_timeout
        while time.time() < deadline:
            result = subprocess.run(["ip", "link", "show", "tun0"], capture_output=True)
            if result.returncode == 0:
                time.sleep(2)
                return True
            time.sleep(1)
        return False

    def _wait_for_tun_down(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            result = subprocess.run(["ip", "link", "show", "tun0"], capture_output=True)
            if result.returncode != 0:
                return
            time.sleep(1)

    def cleanup(self):
        """Ensure VPN is disconnected on exit."""
        if self.enabled:
            try:
                self.disconnect()
            except Exception:
                pass
