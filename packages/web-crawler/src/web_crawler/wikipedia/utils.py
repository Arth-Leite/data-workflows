import asyncio
import functools
import time
from collections import deque


def rate_limited(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        await self.swl.add()
        return await func(self, *args, **kwargs)

    return wrapper


class SlidingWindowLog:
    def __init__(self, n_requests: int, duration: int, minimum_delay: int) -> None:
        self.requests = n_requests
        self.duration = duration
        self.minimum_delay = minimum_delay
        self.queue = deque()
        self.lock = asyncio.Lock()

    async def add(self):
        while True:
            async with self.lock:
                ct = time.time()

                while self.queue and ct - self.queue[0] >= self.duration:
                    self.queue.popleft()

                time_to_wait = None
                if self.queue and ct - self.queue[-1] <= self.minimum_delay:
                    time_to_wait = self.minimum_delay - (ct - self.queue[-1])
                elif self.queue and len(self.queue) >= self.requests:
                    # Wait until the oldest element leaves
                    time_to_wait = self.duration - (ct - self.queue[0])
                else:
                    # Accepted
                    self.queue.append(ct)
                    return

            print(f"Waiting for {time_to_wait}")
            await asyncio.sleep(time_to_wait)
