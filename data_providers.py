#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import psutil
import time

# For GPU monitoring, pynvml is a common choice for NVIDIA
try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

# --- CPU Provider ---
def get_cpu_usage():
    return {"text": f"CPU: {psutil.cpu_percent(interval=None)}%"}

# --- RAM Provider ---
def get_ram_usage():
    mem = psutil.virtual_memory()
    return {
        "text": f"{mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB",
        "percent": mem.percent
    }

# --- Disk Provider ---
def get_disk_space(drive="C:/"):
    try:
        usage = psutil.disk_usage(drive)
        return {
            "text": f"{usage.free / (1024**3):.1f} GB Free",
            "percent": usage.percent
        }
    except FileNotFoundError:
        return {"text": f"Drive '{drive}'\nNot Found", "percent": -1}
    except Exception:
        return {"text": "Disk Error", "percent": -1}

#--------------------------------------------------------------------
# Class Network Provider (Stateful)
#--------------------------------------------------------------------
class NetworkMonitor:
    def __init__(self):
        self.last_check = time.time()
        self.last_io = psutil.net_io_counters()


    def get_speed(self):
        now = time.time()
        current_io = psutil.net_io_counters()
        elapsed = now - self.last_check

        if elapsed < 0.5: # Update at most twice per second
            upload_speed = 0
            download_speed = 0
        else:
            upload_speed = (current_io.bytes_sent - self.last_io.bytes_sent) / elapsed
            download_speed = (current_io.bytes_recv - self.last_io.bytes_recv) / elapsed
            self.last_check = now
            self.last_io = current_io
        
        up_str = self._format_speed(upload_speed)
        down_str = self._format_speed(download_speed)

        return {"text": f"▲ {up_str}\n▼ {down_str}"}


    def _format_speed(self, speed_bytes):
        if speed_bytes > 1024 * 1024:
            return f"{speed_bytes / (1024**2):.1f} MB/s"
        elif speed_bytes > 1024:
            return f"{speed_bytes / 1024:.0f} KB/s"
        else:
            return f"{speed_bytes:.0f} B/s"

#--------------------------------------------------------------------
# Class GpuMonitor (Stateful)
#--------------------------------------------------------------------
class GpuMonitor:
    def __init__(self):
        self.handle = None
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                # Assumes one GPU; a multi-GPU setup would require more logic.
                self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except pynvml.NVMLError:
                self.handle = None # Fail gracefully


    def get_info(self):
        if not self.handle:
            return {"text": "NVIDIA GPU\nNot Found"}
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
            temp = pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)
            return {"text": f"GPU: {util.gpu}%\nTemp: {temp}°C"}
        except pynvml.NVMLError:
            return {"text": "GPU Error"}


    def shutdown(self):
        if PYNVML_AVAILABLE and self.handle:
            pynvml.nvmlShutdown()

# --- Provider Registration ---
# Instantiate stateful monitors
network_monitor = NetworkMonitor()
gpu_monitor = GpuMonitor()

# Map provider names from config to their handler functions
PROVIDER_MAP = {
    "clock": lambda: {"text": time.strftime("%H:%M:%S")},
    "cpu_usage": get_cpu_usage,
    "ram_usage": get_ram_usage,
    "disk_space": get_disk_space,
    "network_speed": network_monitor.get_speed,
    "gpu_info": gpu_monitor.get_info,
}