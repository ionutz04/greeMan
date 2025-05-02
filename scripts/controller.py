import asyncio
import logging
import signal
import subprocess
import re
import json
import datetime
from greeclimate.discovery import Discovery
from greeclimate.device import Device, Mode

# Configure logging to both file and console
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
# file_handler = logging.FileHandler('./logs/ac_controller.log')
# file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Add handlers
# logger.addHandler(file_handler)
logger.addHandler(console_handler)

_LOGGER = logging.getLogger(__name__)

# Global state tracking
current_state = {
    'power': False,
    'target_temp': 22.0  # Default temperature when starting AC
}
running = True

def get_snmp_temperature():
    """Get current temperature from SNMP sensor"""
    command = [
        'snmpget',
        '-v', '2c',
        '-c', 'public',
        '192.168.0.100',
        '1.3.6.1.4.1.17095.5.2.0'
    ]
    
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Extract numerical value from response
        output = result.stdout.strip()
        match = re.search(r'(?:STRING|INTEGER|GAUGE|Counter32):\s+["]?([0-9.]+)', output)
        
        if match:
            value = match.group(1)
            return float(value) if '.' in value else int(value)
        else:
            raise ValueError("No numerical value found in SNMP response")
            
    except subprocess.CalledProcessError as e:
        _LOGGER.error(f"SNMP Error: {e.stderr.strip()}")
        return None
    except Exception as e:
        _LOGGER.error(f"Temperature read error: {str(e)}")
        return None
def load_config(config_path='ac_config.json'):
    try:
        with open(config_path, 'r') as config_file:
            return json.load(config_file)
    except Exception as e:
        _LOGGER.error(f"Failed to load configuration: {str(e)}")
        # Return default values if config file can't be loaded
        return {
            "temperature_on": 24.0,
            "temperature_off": 22.5,
            "restricted_time": {
                "start": "21:00",
                "end": "10:00"
            }
        }
async def discover_and_bind():
    """Discover and bind to the first available Gree device"""
    try:
        discovery = Discovery()
        devices = await discovery.scan(wait_for=5)
        if not devices:
            _LOGGER.error("No Gree devices found on network")
            return None

        device_info = devices[0]
        _LOGGER.info("Found device: %s (%s:%d)",
                    device_info.name,
                    device_info.ip,
                    device_info.port)

        device = Device(device_info)
        await device.bind()
        return device

    except Exception as e:
        _LOGGER.error("Discovery failed: %s", str(e))
        return None

async def set_ac_state(device: Device, power: bool):
    """Control AC power state with default temperature"""
    global current_state
    
    try:
        if power:
            device.mode = Mode.Cool
            device.target_temperature = current_state['target_temp']
            
        device.power = power
        await device.push_state_update()
        current_state['power'] = power
        _LOGGER.info("AC %s at %.1f°C", "ON" if power else "OFF", current_state['target_temp'])
        
    except Exception as e:
        _LOGGER.error("Failed to set AC state: %s", str(e))
def is_time_restricted(config):
    """Check if current time is within the restricted period"""
    now = datetime.datetime.now().time()
    
    # Parse restricted time periods from config
    start_time = datetime.datetime.strptime(config["restricted_time"]["start"], "%H:%M").time()
    end_time = datetime.datetime.strptime(config["restricted_time"]["end"], "%H:%M").time()
    
    # Handle overnight restrictions (e.g., 21:00 to 10:00)
    if start_time > end_time:
        return now >= start_time or now <= end_time
    # Handle same-day restrictions (e.g., 13:00 to 15:00)
    else:
        return start_time <= now <= end_time

async def temperature_control_loop(device: Device, check_interval=60):
    """Main control loop with proper hysteresis and time-based restrictions"""
    while running:
        # Reload configuration on each iteration to catch any changes
        config = load_config()
        
        # Extract configuration values
        temp_on = config["temperature_on"]
        temp_off = config["temperature_off"]
        
        current_temp = get_snmp_temperature()
        if current_temp is None:
            _LOGGER.warning("Failed to read temperature, retrying...")
            await asyncio.sleep(check_interval)
            continue

        _LOGGER.info(f"Current temperature: {current_temp:.1f}°C")
        
        try:
            await device.update_state()
            actual_power = device.power
        except Exception as e:
            _LOGGER.error(f"State update failed: {str(e)}")
            actual_power = current_state['power']

        current_state['power'] = actual_power
        
        # Check if current time is within restricted period
        time_restricted = is_time_restricted(config)
        
        # Turn on AC if:
        # 1. Temperature is above threshold
        # 2. AC is not already running
        # 3. Current time is NOT within restricted period
        if current_temp > temp_on and not actual_power and not time_restricted:
            _LOGGER.info(f"Temperature above {temp_on}°C - starting AC")
            await set_ac_state(device, True)
            
        # Turn off AC if:
        # 1. Temperature is below threshold OR time is within restricted period
        # 2. AC is currently running
        elif (current_temp < temp_off or time_restricted) and actual_power:
            reason = f"Temperature below {temp_off}°C" if current_temp < temp_off else "Within restricted time period"
            _LOGGER.info(f"{reason} - stopping AC")
            await set_ac_state(device, False)

        await asyncio.sleep(check_interval)


def shutdown(signum, frame):
    """Handle shutdown signals"""
    global running
    _LOGGER.info("Shutting down...")
    running = False

async def main():
    global running
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    device = await discover_and_bind()
    if not device:
        return

    control_task = asyncio.create_task(temperature_control_loop(device))

    while running:
        await asyncio.sleep(1)

    control_task.cancel()
    try:
        await control_task
    except asyncio.CancelledError:
        pass

    _LOGGER.info("Clean shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
