import logging
from swarm import Agent, Swarm
from typing import Dict, Any, Optional
from decimal import Decimal
from web3 import Web3
from django.conf import settings
from pydantic import Field, ConfigDict
from data.market_data import MarketDataService

logger = logging.getLogger(__name__)

# Define pool configurations
AVALANCHE_LP_POOLS = {
    "AVAX_USDC": {
        "name": "AVAX-USDC",
        "pair_address": "0xd446eb1660f766d533beceef890df7a69d26f7d1",
        "router": "0xb4315e873dBcf96Ffd0acd8EA43f689D8c20fB30",
        "bin_step": 20,
        "tokens": {
            "tokenX": {
                "symbol": "AVAX",
                "address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",  # WAVAX
                "decimals": 18
            },
            "tokenY": {
                "symbol": "USDC",
                "address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
                "decimals": 6
            }
        }
    },
    "AVAX_USDT": {
        "name": "AVAX-USDT",
        "pair_address": "0x...",  # Add actual address
        "router": "0xb4315e873dBcf96Ffd0acd8EA43f689D8c20fB30",
        "bin_step": 20,
        "tokens": {
            "tokenX": {
                "symbol": "AVAX",
                "address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
                "decimals": 18
            },
            "tokenY": {
                "symbol": "USDT",
                "address": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
                "decimals": 6
            }
        }
    }
}

class LiquidityProviderAgent(Agent):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    market_data: Optional[MarketDataService] = Field(default=None)
    
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING AVALANCHE LP AGENT")
        logger.info("="*50)
        
        super().__init__(
            name="Avalanche LP Assistant",
            model="gpt-4",
            instructions="""You are a liquidity provider assistant for Trader Joe V2 pools on Avalanche.
            
            Available pools:
            - AVAX-USDC
            - AVAX-USDT
            
            You must understand user intentions naturally. Users might express their desire to add liquidity in many ways:
            - Direct: "I want to add liquidity"
            - Indirect: "I want to provide liquidity"
            - Implied: "I want to invest in the pool"
            - Context-based: If they ask about a specific pool and don't mention removal, assume they want to add
            
            IMPORTANT:
            - Understand context from the entire conversation
            - If user mentions a pool without specifying action, they likely want to add liquidity
            - Only assume removal when explicitly mentioned
            - If amounts aren't specified, ask for them
            
            ALWAYS use:
            - prepare_add_liquidity for ANY addition/investment intention
            - prepare_remove_liquidity ONLY when explicitly requested""",
            functions=[
                self.prepare_add_liquidity,
                self.prepare_remove_liquidity
            ]
        )
        object.__setattr__(self, 'market_data', MarketDataService())

    async def prepare_add_liquidity(
        self, 
        pool_key: str,
        token_x_amount: float, 
        token_y_amount: float, 
        price_range: Dict = None
    ) -> Dict[str, Any]:
        """Prepare transaction details for adding liquidity"""
        try:
            # Get pool configuration
            pool_config = AVALANCHE_LP_POOLS.get(pool_key)
            if not pool_config:
                raise ValueError(f"Pool configuration not found for {pool_key}")

            # Get current pool data
            active_id = await self.market_data.get_active_bin_id(pool_config["pair_address"])
            pool_data = await self.market_data.get_pool_metrics(pool_config["pair_address"])
            current_price = float(pool_data['current_price'])
            
            # Convert amounts to Wei/Units based on decimals
            token_x_decimals = pool_config["tokens"]["tokenX"]["decimals"]
            token_y_decimals = pool_config["tokens"]["tokenY"]["decimals"]
            
            amount_x_wei = int(token_x_amount * (10 ** token_x_decimals))
            amount_y_wei = int(token_y_amount * (10 ** token_y_decimals))
            
            # Calculate distribution based on price range
            delta_ids = [-1, 0, 1]  # Default range around active bin
            if price_range:
                min_bin = self._price_to_bin_id(price_range['min'], pool_config["bin_step"])
                max_bin = self._price_to_bin_id(price_range['max'], pool_config["bin_step"])
                delta_ids = list(range(min_bin - active_id, max_bin - active_id + 1))
            
            # Calculate distributions
            PRECISION = 10**18
            distribution_x = [PRECISION // 2] * len(delta_ids)
            distribution_y = [PRECISION // 2] * len(delta_ids)
            
            liquidity_params = {
                "tokenX": pool_config["tokens"]["tokenX"]["address"],
                "tokenY": pool_config["tokens"]["tokenY"]["address"],
                "binStep": pool_config["bin_step"],
                "amountX": str(amount_x_wei),
                "amountY": str(amount_y_wei),
                "amountXMin": str((amount_x_wei * 99) // 100),  # 1% slippage
                "amountYMin": str((amount_y_wei * 99) // 100),  # 1% slippage
                "activeIdDesired": active_id,
                "idSlippage": 5,
                "deltaIds": delta_ids,
                "distributionX": distribution_x,
                "distributionY": distribution_y,
                "to": "${USER_ADDRESS}",
                "refundTo": "${USER_ADDRESS}",
                "deadline": "${DEADLINE}"
            }
            
            return {
                "type": "add_liquidity",
                "network": "avalanche",
                "chain_id": 43114,
                "pool": pool_config,
                "router_address": pool_config["router"],
                "pair_address": pool_config["pair_address"],
                "liquidity_params": liquidity_params,
                "required_approvals": [
                    {
                        "token": pool_config["tokens"]["tokenY"]["symbol"],
                        "address": pool_config["tokens"]["tokenY"]["address"],
                        "amount": str(amount_y_wei),
                        "spender": pool_config["router"]
                    }
                ],
                "metadata": {
                    "current_price": current_price,
                    "active_bin_id": active_id,
                    "price_range": price_range,
                    "expected_position": {
                        "token_x": token_x_amount,
                        "token_y": token_y_amount
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error preparing add liquidity transaction: {str(e)}")
            return {"error": str(e)}

    def _price_to_bin_id(self, price: float, bin_step: int) -> int:
        """Convert price to bin ID using pool's binStep"""
        # Implement proper bin ID calculation based on Trader Joe V2 docs
        # This is a placeholder - need actual formula
        return int(price * bin_step)

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process incoming messages and route to appropriate LP function"""
        try:
            # Extract pool from message
            message_lower = message.lower()
            selected_pool = None
            
            # First, try to find the pool from the message
            for pool_key, pool_data in AVALANCHE_LP_POOLS.items():
                tokens = [t["symbol"].lower() for t in pool_data["tokens"].values()]
                if all(token.lower() in message_lower for token in tokens):
                    selected_pool = pool_key
                    break
            
            if not selected_pool:
                return {
                    "error": "Could not determine which pool you want to use",
                    "available_pools": list(AVALANCHE_LP_POOLS.keys())
                }

            # Use AI to understand intent and extract amounts
            client = Swarm()
            response = client.run(
                agent=self,
                messages=[{"role": "user", "content": message}]
            )

            # Check for tool calls in the response
            tool_calls = response.messages[0].get('tool_calls', [])
            if tool_calls:
                # Extract function arguments
                import json
                args = json.loads(tool_calls[0]['function']['arguments'])
                
                if args.get('token_x_amount') is not None and args.get('token_y_amount') is not None:
                    return await self.prepare_add_liquidity(
                        pool_key=selected_pool,
                        token_x_amount=float(args['token_x_amount']),
                        token_y_amount=float(args['token_y_amount']),
                        price_range=args.get('price_range')
                    )

            # If no amounts were found, ask for them
            pool_name = AVALANCHE_LP_POOLS[selected_pool]["name"]
            return {
                "type": "request_amounts",
                "message": f"How much would you like to add to the {pool_name} pool? Please specify the amounts for both tokens.",
                "pool": AVALANCHE_LP_POOLS[selected_pool]
            }

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {"error": str(e)}

    async def prepare_remove_liquidity(self, pool_key: str) -> Dict[str, Any]:
        """Prepare transaction details for removing liquidity"""
        try:
            # Get pool configuration
            pool_config = AVALANCHE_LP_POOLS.get(pool_key)
            if not pool_config:
                raise ValueError(f"Pool configuration not found for {pool_key}")

            return {
                "type": "remove_liquidity",
                "network": "avalanche",
                "chain_id": 43114,
                "pool": pool_config,
                "router_address": pool_config["router"],
                "pair_address": pool_config["pair_address"],
                "message": "Please implement remove liquidity functionality"
            }
            
        except Exception as e:
            logger.error(f"Error preparing remove liquidity transaction: {str(e)}")
            return {"error": str(e)}
