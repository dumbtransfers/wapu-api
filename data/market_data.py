from typing import Dict, Any, Optional,List
from decimal import Decimal
from datetime import datetime, timedelta
import aiohttp
from dataclasses import dataclass
from django.conf import settings
import asyncio
from web3 import Web3
from web3.providers import HTTPProvider
from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider
import numpy as np
import logging

logger = logging.getLogger(__name__)

@dataclass
class PoolMetrics:
    """Data class for pool metrics"""
    tvl: Decimal
    volume_24h: Decimal
    fees_24h: Decimal
    apr: Decimal
    volatility: float
    price_range: Dict[str, Decimal]
    liquidity_distribution: Dict[str, Decimal]
    il_7d: float

@dataclass
class RiskMetrics:
    """Data class for risk metrics"""
    volatility_score: float
    liquidity_score: float
    il_risk_score: float
    overall_risk: float
    risk_factors: Dict[str, Any]

class MarketDataService:
    def __init__(self):
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(settings.AVALANCHE_RPC_URL))
        self.async_w3 = AsyncWeb3(AsyncHTTPProvider(settings.AVALANCHE_RPC_URL))

        # Contract addresses
        self.trader_joe_factory = settings.TRADER_JOE_FACTORY_ADDRESS
        self.trader_joe_router = settings.TRADER_JOE_ROUTER_ADDRESS
        
        # Known pools for testing/validation
        self.known_pools = {
            'AVAX-USDC': settings.AVAX_USDC_POOL,
            'USDT-USDC': settings.USDT_USDC_POOL
        }
        
        logger.info(f"Initialized MarketDataService with known pools: {self.known_pools}")
        
        # Load ABIs
        self.factory_abi = settings.TRADER_JOE_FACTORY_ABI
        self.pool_abi = settings.TRADER_JOE_POOL_ABI
        
        # Initialize contracts
        self.factory_contract = self.w3.eth.contract(
            address=self.trader_joe_factory,
            abi=self.factory_abi
        )
        
        # Cache settings
        self.cache = {}
        self.cache_duration = 300  # 5 minutes
        
    async def get_pool_metrics(self, pool_address: str) -> PoolMetrics:
        """Get current pool metrics from DEX"""
        # Validate pool address
        if pool_address not in self.known_pools.values():
            logger.warning(f"Unknown pool address: {pool_address}")
            # You might want to add additional validation here
        
        logger.info(f"Fetching metrics for pool: {pool_address}")
        
        cache_key = f"pool_metrics_{pool_address}"
        cached_data = self._get_from_cache(cache_key)
        
        if cached_data:
            return cached_data
            
        try:
            # Get pool data from DEX subgraph
            async with self.session.get(
                f"{self.base_url}/pools/{pool_address}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch pool data: {await response.text()}")
                    
                data = await response.json()
                
            # Get additional metrics from on-chain
            additional_metrics = await self._get_onchain_metrics(pool_address)
            
            # Calculate derived metrics
            apr = self._calculate_apr(data, additional_metrics)
            volatility = self._calculate_volatility(data['price_history'])
            il_risk = self._calculate_il_risk(data['price_history'])
            
            pool_metrics = PoolMetrics(
                tvl=Decimal(str(data['tvlUSD'])),
                volume_24h=Decimal(str(data['volume24h'])),
                fees_24h=Decimal(str(data['fees24h'])),
                apr=Decimal(str(apr)),
                volatility=volatility,
                price_range={
                    'min': Decimal(str(data['price_range']['min'])),
                    'max': Decimal(str(data['price_range']['max'])),
                    'current': Decimal(str(data['price_range']['current']))
                },
                liquidity_distribution=self._process_liquidity_distribution(data['ticks']),
                il_7d=il_risk
            )
            
            # Cache the result
            self._add_to_cache(cache_key, pool_metrics)
            
            return pool_metrics
            
        except Exception as e:
            raise Exception(f"Error fetching pool metrics: {str(e)}")
            
    async def get_risk_metrics(self, pool_address: str) -> RiskMetrics:
        """Calculate risk metrics for pool"""
        try:
            # Get pool metrics first
            pool_metrics = await self.get_pool_metrics(pool_address)
            
            # Calculate risk scores
            volatility_score = self._calculate_volatility_score(pool_metrics.volatility)
            liquidity_score = self._calculate_liquidity_score(pool_metrics.tvl)
            il_risk_score = self._calculate_il_risk_score(pool_metrics.il_7d)
            
            # Calculate overall risk
            overall_risk = (volatility_score + liquidity_score + il_risk_score) / 3
            
            # Identify risk factors
            risk_factors = self._identify_risk_factors(pool_metrics)
            
            return RiskMetrics(
                volatility_score=volatility_score,
                liquidity_score=liquidity_score,
                il_risk_score=il_risk_score,
                overall_risk=overall_risk,
                risk_factors=risk_factors
            )
            
        except Exception as e:
            raise Exception(f"Error calculating risk metrics: {str(e)}")
            
    def _calculate_volatility_score(self, volatility: float) -> float:
        """Convert volatility to 0-1 risk score"""
        # Higher volatility = higher risk
        return min(volatility * 10, 1.0)  # Cap at 1.0
        
    def _calculate_liquidity_score(self, tvl: Decimal) -> float:
        """Convert TVL to 0-1 risk score"""
        # Lower TVL = higher risk
        min_tvl = Decimal('100000')  # $100k minimum
        return float(min(min_tvl / tvl, 1.0))  # Cap at 1.0
        
    def _calculate_il_risk_score(self, il_7d: float) -> float:
        """Convert IL to 0-1 risk score"""
        # Higher IL = higher risk
        return min(il_7d * 20, 1.0)  # Cap at 1.0
        
    def _identify_risk_factors(self, metrics: PoolMetrics) -> Dict[str, Any]:
        """Identify specific risk factors"""
        factors = {}
        
        # Check volatility
        if metrics.volatility > 0.02:  # 2%
            factors['high_volatility'] = {
                'level': 'high',
                'value': metrics.volatility
            }
            
        # Check liquidity
        if metrics.tvl < Decimal('100000'):
            factors['low_liquidity'] = {
                'level': 'high',
                'value': metrics.tvl
            }
            
        # Check IL risk
        if metrics.il_7d > 0.05:  # 5%
            factors['high_il_risk'] = {
                'level': 'high',
                'value': metrics.il_7d
            }
            
        return factors
        
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get data from cache if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now().timestamp() - timestamp < self.cache_duration:
                return data
        return None
        
    def _add_to_cache(self, key: str, data: Any):
        """Add data to cache"""
        self.cache[key] = (data, datetime.now().timestamp()) 
        
    async def _get_onchain_metrics(self, pool_address: str) -> Dict[str, Any]:
        """Get pool metrics directly from blockchain"""
        try:
            # Initialize pool contract
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=self.pool_abi
            )
            
            # Get pool state
            active_id = await pool_contract.functions.getActiveId().call()
            bin_step = await pool_contract.functions.getBinStep().call()
            
            # Get reserves and liquidity distribution
            bins_data = []
            for bin_id in range(active_id - 10, active_id + 11):  # Get 20 bins around active
                try:
                    bin_reserve = await pool_contract.functions.getBin(bin_id).call()
                    bins_data.append({
                        'id': bin_id,
                        'x': bin_reserve[0],  # Token X reserve
                        'y': bin_reserve[1],  # Token Y reserve
                    })
                except Exception:
                    continue
            
            # Get tokens info
            token_x = await pool_contract.functions.getTokenX().call()
            token_y = await pool_contract.functions.getTokenY().call()
            
            # Get fees info
            fees_x = await pool_contract.functions.getFeesX().call()
            fees_y = await pool_contract.functions.getFeesY().call()
            
            return {
                'active_id': active_id,
                'bin_step': bin_step,
                'bins': bins_data,
                'tokens': {
                    'x': token_x,
                    'y': token_y
                },
                'fees': {
                    'x': fees_x,
                    'y': fees_y
                }
            }
            
        except Exception as e:
            raise Exception(f"Error fetching onchain metrics: {str(e)}")

    def _calculate_apr(self, data: Dict, onchain_data: Dict) -> Decimal:
        """Calculate APR based on fees and TVL"""
        try:
            # Get daily fees
            daily_fees_usd = Decimal(str(data['fees24h']))
            
            # Annualize
            yearly_fees = daily_fees_usd * 365
            
            # Calculate APR
            tvl = Decimal(str(data['tvlUSD']))
            if tvl > 0:
                apr = (yearly_fees / tvl) * 100
                return apr
            return Decimal('0')
            
        except Exception as e:
            raise Exception(f"Error calculating APR: {str(e)}")

    def _calculate_volatility(self, price_history: List[Dict]) -> float:
        """Calculate price volatility from historical data"""
        try:
            if not price_history:
                return 0.0
                
            prices = [float(p['price']) for p in price_history]
            returns = np.diff(np.log(prices))
            return float(np.std(returns) * np.sqrt(365))
            
        except Exception as e:
            raise Exception(f"Error calculating volatility: {str(e)}")

    def _calculate_il_risk(self, price_history: List[Dict]) -> float:
        """Calculate impermanent loss risk"""
        try:
            if not price_history:
                return 0.0
                
            start_price = float(price_history[0]['price'])
            end_price = float(price_history[-1]['price'])
            
            price_ratio = end_price / start_price
            il = 2 * np.sqrt(price_ratio) / (1 + price_ratio) - 1
            
            return float(abs(il))
            
        except Exception as e:
            raise Exception(f"Error calculating IL risk: {str(e)}")

    def _process_liquidity_distribution(self, bins: List[Dict]) -> Dict[str, Decimal]:
        """Process liquidity distribution from bin data"""
        try:
            total_liquidity = sum(float(bin['x']) + float(bin['y']) for bin in bins)
            
            distribution = {}
            for bin in bins:
                bin_liquidity = float(bin['x']) + float(bin['y'])
                distribution[str(bin['id'])] = Decimal(str(bin_liquidity / total_liquidity))
                
            return distribution
            
        except Exception as e:
            raise Exception(f"Error processing liquidity distribution: {str(e)}")