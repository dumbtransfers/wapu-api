class BlockchainScanner:
    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider(settings.WEB3_PROVIDER))
        self.event_processors = {}
    
    async def monitor_events(self, contract_address: str, event_abi: Dict):
        """Monitor blockchain events for specific contract"""
        contract = self.web3.eth.contract(
            address=contract_address,
            abi=event_abi
        )
        
        async for event in contract.events.all_events.create_filter().get_all_entries():
            await self._process_event(event)