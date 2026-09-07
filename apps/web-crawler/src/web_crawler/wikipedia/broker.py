import os
from abc import ABC

import aio_pika


class MessageBroker(ABC):
    async def get_new_message(self):
        pass

    async def publish_message(self, message: str):
        pass

    async def ack_message(self, message):
        pass

    @classmethod
    def create(cls) -> "MessageBroker":
        pass


class RabbitBroker(MessageBroker):
    def __init__(self) -> None:
        self.queue = None
        self.channel = None
        self.message_ref_dict = dict()

    async def setup(self):
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        self.connection = await aio_pika.connect(f"amqp://admin:admin@{rabbitmq_host}/")
        self.channel = await self.connection.channel()
        self.queue = await self.channel.declare_queue("titles", durable=True)
        self.message_count = self.queue.declaration_result.message_count or 0

    async def get_message(self) -> str:
        if self.queue is None:
            await self.setup()

        message_ref = await self.queue.get(
            no_ack=False,  # no_ack=True means autoack once the message is delivered
            fail=False,
            timeout=10,
        )
        self.message_ref_dict[message_ref.body.decode("utf-8")] = message_ref
        return message_ref.body.decode("utf-8")

    async def ack_message(self, message: str):
        message_ref = self.message_ref_dict[message]
        await message_ref.ack()
        self.message_count -= 1

    async def publish_message(self, message: str) -> None:
        if self.channel is None:
            await self.setup()

        await self.channel.default_exchange.publish(
            message=aio_pika.Message(body=message.encode("utf-8"), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=self.queue.name,
        )
        self.message_count += 1

    async def is_queue_drained(self) -> bool:
        if self.message_count == 0:
            self.channel.close()
            return True
        else:
            return False
