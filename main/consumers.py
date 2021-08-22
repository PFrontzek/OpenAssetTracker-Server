from channels.generic.websocket import AsyncJsonWebsocketConsumer


class UserUpdateConsumer(AsyncJsonWebsocketConsumer):
    groups = ("user",)
    user_id: int

    async def connect(self):
        self.user_id = self.scope["user"].id
        await self.accept()

    async def disconnect(self, code):
        return await super().disconnect(code)

    async def user_update(self, event: dict):
        if event["user"] == self.user_id:
            await self.send_json({"device": event["device"]})
        pass

    async def a(self, event):
        print("test")
        await self.send_json({"b": "bbbbb"})


class DeviceUpdateConsumer(AsyncJsonWebsocketConsumer):
    groups = "device"
    imei: int

    async def connect(self):
        self.imei = self.scope["url_route"]["kwargs"]["imei"]
        print(self.scope)
        await self.accept()
        print("connected")

    async def disconnect(self, code):
        print("disconnected")
        return await super().disconnect(code)

    async def receive_json(self, content, **kwargs):
        print(content)
        print(self.channel_layer)
        await self.channel_layer.group_send("a", {"type": "aa", "message": "test"})
        return await super().receive_json(content, **kwargs)

    async def aa(self, event):
        await self.send_json({"a": "aaaaa"})
        print("send")
        print(event)
        print("öööö")
        from channels.layers import get_channel_layer

        await get_channel_layer("default").group_send("a", {"type": "b", "message": "zweiter"})

    async def b(self, event):
        print(event)

    async def device_update(self, event: dict):

        pass
