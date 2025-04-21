#!/usr/bin/env python3
import asyncio
import logging
import signal
from greeclimate.discovery import Discovery
from greeclimate.device import Device

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Global state tracking
current_state = {
    'power': False,
    'temp': 25.0,
    'mode': 'cool'
}
running = True

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

async def sync_state(device: Device):
    """Synchronize device state with our virtual state"""
    try:
        # Get fresh state from device
        await device.update_state()
        
        # Check for mismatches
        if device.power != current_state['power']:
            _LOGGER.warning("Power state mismatch! Device: %s vs Virtual: %s",
                          device.power, current_state['power'])
            
        if device.target_temperature != current_state['temp']:
            _LOGGER.warning("Temp mismatch! Device: %s vs Virtual: %s",
                          device.target_temperature, current_state['temp'])
            
        # Update virtual state from device (only if not overridden)
        current_state.update({
            'power': device.power,
            'temp': device.target_temperature,
            'mode': device.mode.name.lower()
        })
        
    except Exception as e:
        _LOGGER.error("State sync failed: %s", str(e))

async def periodic_sync(device: Device, interval=60):
    """Periodic state synchronization"""
    while running:
        await asyncio.sleep(interval)
        await sync_state(device)
        _LOGGER.debug("Periodic sync completed")

async def example_control_loop(device: Device, interval=30):
    """Example control logic - toggle power every 30 seconds"""
    while running:
        # Toggle power state
        new_power = not current_state['power']
        try:
            device.power = new_power
            await device.push_state_update()
            current_state['power'] = new_power
            _LOGGER.info("Power toggled to %s", new_power)
        except Exception as e:
            _LOGGER.error("Failed to toggle power: %s", str(e))
        
        await asyncio.sleep(interval)

def shutdown(signum, frame):
    """Handle shutdown signals"""
    global running
    _LOGGER.info("Shutting down...")
    running = False

async def main():
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Discover and bind device
    device = await discover_and_bind()
    if not device:
        return

    # Initial state sync
    await sync_state(device)
    _LOGGER.info("Initial state: %s", current_state)

    # Start background tasks
    sync_task = asyncio.create_task(periodic_sync(device))
    control_task = asyncio.create_task(example_control_loop(device))

    # Keep running until shutdown
    while running:
        await asyncio.sleep(1)

    # Cleanup
    sync_task.cancel()
    control_task.cancel()
    try:
        await sync_task
        await control_task
    except asyncio.CancelledError:
        pass

    _LOGGER.info("Clean shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
