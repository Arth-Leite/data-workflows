import asyncio
import os
from abc import ABC

import aio_pika
import redis.asyncio as redis


class Frontier(ABC):
    def __init__(self) -> None:
        self.wait_queue_drained = asyncio.Event()

    async def get_message(self):
        pass

    async def publish_message(self, message: str):
        pass

    async def ack_message(self, message):
        pass

    async def has_visited(self, content: str):
        pass

    async def mark_as_visited(self, content: str):
        pass

    @classmethod
    def create(cls) -> "Frontier":
        pass


class RabbitRedisFrontier(Frontier):
    def __init__(self) -> None:
        super().__init__()
        self.queue = None
        self.channel = None
        self.message_ref_dict = dict()

    async def setup(self):
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        self.connection = await aio_pika.connect(f"amqp://admin:admin@{rabbitmq_host}/")
        self.channel = await self.connection.channel()
        self.queue = await self.channel.declare_queue("titles", durable=True)
        self.message_count = self.queue.declaration_result.message_count or 0

        self.redis = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"))
        self.redis_set = "wikipedia"

    async def has_visited(self, content: str):
        ismember = await self.redis.sismember(self.redis_set, content)
        if ismember == 1:
            return True
        else:
            return False

    async def mark_as_visited(self, content: str):
        await self.redis.sadd(self.redis_set, content)

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
        if self.message_count == 0:
            self.wait_queue_drained.set()

    async def publish_message(self, message: str) -> None:
        if self.channel is None:
            await self.setup()

        await self.channel.default_exchange.publish(
            message=aio_pika.Message(body=message.encode("utf-8"), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=self.queue.name,
        )
        self.message_count += 1
