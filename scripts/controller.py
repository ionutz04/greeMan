import asyncio
import logging
import signal
import subprocess
import re
from greeclimate.discovery import Discovery
from greeclimate.device import Device, Mode

# Configure logging to both file and console
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler
file_handler = logging.FileHandler('./logs/ac_controller.log')
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

_LOGGER = logging.getLogger(__name__)

# Global state tracking
current_state = {
    'power': False,
    'target_temp': 23.0  # Default temperature when starting AC
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

async def temperature_control_loop(device: Device, check_interval=60):
    """Main control loop with proper hysteresis"""
    while running:
        current_temp = get_snmp_temperature()
        if current_temp is None:
            _LOGGER.warning("Failed to read temperature, retrying...")
            await asyncio.sleep(check_interval)
            continue

        _LOGGER.info("Current temperature: %.1f°C", current_temp)
        
        try:
            await device.update_state()
            actual_power = device.power
        except Exception as e:
            _LOGGER.error("State update failed: %s", str(e))
            actual_power = current_state['power']

        current_state['power'] = actual_power
        
        if current_temp > 24 and not actual_power:
            _LOGGER.info("Temperature above 24°C - starting AC")
            await set_ac_state(device, True)
            
        elif current_temp < 23 and actual_power:
            _LOGGER.info("Temperature below 23°C - stopping AC")
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
