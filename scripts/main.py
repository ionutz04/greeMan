import asyncio
from greeclimate.discovery import Discovery
from greeclimate.device import Device
from greeclimate.device import Mode
# async def main():
#     discovery = Discovery()
#     for device_info in await discovery.scan(wait_for=5):
#         device = Device(device_info)
#         # if device:
#         #     break
#         await device.bind()
#         print(f"{device.device_info.ip} {device.device_info.name} {device.device_info.port}")
#         # device.power=True
#         # device.mode = Mode.Cool
#         # device.target_temperature = 22
#         # print(device.current_temperature)
#         # device.target_temperature = 23
#         # device.power=False
#         # power_state = "OFF" if device.power else "ON"
#         # await device.push_state_update()
#         await device.update_state()
#         print(device.power)
async def main():
    discovery = Discovery()
    devices = await discovery.scan(wait_for=5)
    for device_info in devices:
        device = Device(device_info)
        await device.bind()
        print("Turning power ON via network...")
        device.power = False
        await device.push_state_update()
if __name__ == "__main__":
    asyncio.run(main())
