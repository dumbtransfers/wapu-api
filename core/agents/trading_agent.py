import logging
from swarm import Agent
from typing import Dict, Any, Optional
from decimal import Decimal
from web3 import Web3
from django.conf import settings
from pydantic import Field, ConfigDict
from data.market_data import MarketDataService

logger = logging.getLogger(__name__)

class TradingAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    market_data: Optional[MarketDataService] = Field(default=None)
    
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING TRADING AGENT FOR AVAX-USDC POOL")
        logger.info("="*50)
        
        super().__init__(
            name="Sofia Trading Assistant",
            model="gpt-4",
            instructions="""You are a trading assistant that helps users interact with the AVAX-USDC pool on Trader Joe.
            
            IMPORTANT FUNCTION USAGE RULES:
            1. ALWAYS use prepare_add_liquidity for adding liquidity requests
            2. ALWAYS use prepare_remove_liquidity for removing liquidity requests
            3. ALWAYS use prepare_swap for swap requests
            
            Examples:
            - "I want to add 10 AVAX and 150 USDC to the pool" -> use prepare_add_liquidity
            - "Remove my liquidity position" -> use prepare_remove_liquidity
            - "Swap 5 AVAX for USDC" -> use prepare_swap
            
            Always provide complete transaction details and necessary approvals.""",
            functions=[
                self.prepare_add_liquidity,
                self.prepare_remove_liquidity,
                self.prepare_swap
            ]
        )
        object.__setattr__(self, 'market_data', MarketDataService())

    async def prepare_add_liquidity(self, avax_amount: float, usdc_amount: float, price_range: Dict = None) -> Dict[str, Any]:
        """Prepare transaction details for adding liquidity"""
        try:
            # Get current pool data
            pool_data = await self.market_data.get_pool_metrics()
            current_price = float(pool_data['current_price'])
            
            # If no price range provided, use default ±5% range
            if not price_range:
                price_range = {
                    'min': current_price * 0.95,
                    'max': current_price * 1.05
                }
            
            # Convert amounts to Wei/Units
            avax_wei = Web3.to_wei(avax_amount, 'ether')
            usdc_units = int(usdc_amount * 1e6)  # USDC has 6 decimals
            
            # Prepare liquidity configuration
            liquidity_config = self._prepare_liquidity_config(
                avax_wei,
                usdc_units,
                price_range['min'],
                price_range['max']
            )
            
            return {
                "network": "avalanche",
                "chain_id": 43114,
                "contract_addresses": {
                    "pool": settings.AVAX_USDC_POOL,
                    "avax": settings.WAVAX_ADDRESS,
                    "usdc": settings.USDC_ADDRESS
                },
                "required_approvals": [
                    {
                        "token": "AVAX",
                        "amount": str(avax_wei),
                        "spender": settings.AVAX_USDC_POOL
                    },
                    {
                        "token": "USDC",
                        "amount": str(usdc_units),
                        "spender": settings.AVAX_USDC_POOL
                    }
                ],
                "transaction": {
                    "to": settings.AVAX_USDC_POOL,
                    "function": "mint",
                    "arguments": {
                        "to": "${USER_ADDRESS}",  # To be replaced by user
                        "liquidityConfigs": liquidity_config,
                        "refundTo": "${USER_ADDRESS}"  # To be replaced by user
                    },
                    "value": str(avax_wei) if avax_amount > 0 else "0"
                },
                "metadata": {
                    "current_price": current_price,
                    "price_range": price_range,
                    "expected_position": {
                        "avax": avax_amount,
                        "usdc": usdc_amount
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error preparing add liquidity transaction: {str(e)}")
            return {"error": str(e)}

    def _prepare_liquidity_config(self, avax_amount: int, usdc_amount: int, min_price: float, max_price: float) -> list:
        """Prepare liquidity configuration for the mint function"""
        # Convert price range to bin IDs
        min_bin_id = self._price_to_bin_id(min_price)
        max_bin_id = self._price_to_bin_id(max_price)
        
        # Create liquidity configuration array
        configs = []
        for bin_id in range(min_bin_id, max_bin_id + 1):
            # Return hex strings instead of bytes
            config = Web3.to_hex(bin_id)[2:].zfill(64)  # Convert to hex string
            configs.append(config)
            
        return configs

    def _price_to_bin_id(self, price: float) -> int:
        """Convert price to bin ID using pool's binStep"""
        # This is a simplified version - actual implementation would need
        # to use the pool's binStep and proper math
        return int(price * 100)  # Example conversion

    async def prepare_remove_liquidity(self, position_id: int = None) -> Dict[str, Any]:
        """Prepare transaction details for removing liquidity"""
        # Implementation for removing liquidity
        pass

    async def prepare_swap(self, token_in: str, amount_in: float, token_out: str) -> Dict[str, Any]:
        """Prepare transaction details for swapping tokens"""
        # Implementation for swapping
        pass

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process incoming messages and route to appropriate trading function"""
        try:
            # Extract amounts and action from message
            message = message.lower()
            
            # Check for add liquidity patterns
            if any(phrase in message for phrase in ["add liquidity", "provide liquidity", "deposit"]):
                # Extract AVAX and USDC amounts using regex
                import re
                avax_match = re.search(r'(\d+\.?\d*)\s*(?:avax|wavax)', message)
                usdc_match = re.search(r'(\d+\.?\d*)\s*(?:usdc|usd)', message)
                
                avax_amount = float(avax_match.group(1)) if avax_match else 0
                usdc_amount = float(usdc_match.group(1)) if usdc_match else 0
                
                # If only one amount is provided, calculate the other based on current price
                if (avax_amount == 0 or usdc_amount == 0) and not (avax_amount == 0 and usdc_amount == 0):
                    pool_data = await self.market_data.get_pool_metrics()
                    current_price = float(pool_data['current_price'])
                    
                    if avax_amount == 0:
                        avax_amount = usdc_amount / current_price
                    else:
                        usdc_amount = avax_amount * current_price
                
                # Get price range from context or use default
                price_range = context.get('price_range') if context else None
                
                return await self.prepare_add_liquidity(avax_amount, usdc_amount, price_range)
                
            # Check for remove liquidity patterns
            elif any(phrase in message for phrase in ["remove liquidity", "withdraw", "exit position"]):
                position_id = context.get('position_id') if context else None
                return await self.prepare_remove_liquidity(position_id)
                
            # Check for swap patterns
            elif any(phrase in message for phrase in ["swap", "trade", "exchange"]):
                # Extract token and amount information
                amount_match = re.search(r'(\d+\.?\d*)\s*(avax|usdc)', message)
                if amount_match:
                    amount = float(amount_match.group(1))
                    token_in = amount_match.group(2).upper()
                    token_out = "USDC" if token_in == "AVAX" else "AVAX"
                    
                    return await self.prepare_swap(token_in, amount, token_out)
            
            return {
                "error": "Could not understand trading action. Please specify if you want to add liquidity, remove liquidity, or swap tokens.",
                "examples": [
                    "Add 10 AVAX and 150 USDC to the pool",
                    "Remove my liquidity position",
                    "Swap 5 AVAX for USDC"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error processing trading message: {str(e)}")
            return {
                "error": f"Failed to process trading request: {str(e)}",
                "message": message,
                "context": context
            }
