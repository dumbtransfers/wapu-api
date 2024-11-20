class PriceStreamManager:
    def __init__(self):
        self.active_streams = {}
        self.subscribers = defaultdict(list)
    
    async def start_price_stream(self, symbol: str):
        """Start real-time price monitoring"""
        if symbol not in self.active_streams:
            stream = await self._create_price_stream(symbol)
            self.active_streams[symbol] = stream
            asyncio.create_task(self._process_stream(symbol))