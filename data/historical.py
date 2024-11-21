from typing import Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from django.conf import settings
from web3 import Web3, AsyncWeb3
from web3.providers import AsyncHTTPProvider
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class HistoricalMetrics:
    """Data class for historical metrics"""
    avg_apr_7d: float
    avg_apr_30d: float
    volume_trend: Dict[str, Any]
    impermanent_loss_7d: float
    impermanent_loss_30d: float
    price_correlation: float
    price_volatility: float
    key_levels: Dict[str, Decimal]

class HistoricalDataService:
    def __init__(self):
        # Initialize Web3
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.AVALANCHE_RPC_URL))
        
        # Initialize contracts
        self.pool_abi = settings.TRADER_JOE_POOL_ABI
        self.factory_address = settings.TRADER_JOE_FACTORY_ADDRESS
        self.known_pools = {
            'AVAX-USDC': settings.AVAX_USDC_POOL,
            'USDT-USDC': settings.USDT_USDC_POOL
        }
        
        self.time_windows = {
            '24h': timedelta(days=1),
            '7d': timedelta(days=7),
            '30d': timedelta(days=30)
        }
        
        logger.info(f"Initialized HistoricalDataService with known pools: {self.known_pools}")

    async def get_pool_history(self, pool_address: str) -> HistoricalMetrics:
        """Get historical pool performance data"""
        try:
            logger.info(f"Fetching historical data for pool: {pool_address}")
            
            # Validate pool
            if pool_address not in self.known_pools.values():
                logger.warning(f"Unknown pool address: {pool_address}")
            
            # Initialize pool contract
            pool_contract = self.w3.eth.contract(
                address=pool_address,
                abi=self.pool_abi
            )
            
            # Get current block
            current_block = await self.w3.eth.block_number
            logger.info(f"Current block: {current_block}")
            
            # Calculate blocks for time windows (assuming 2s block time on Avalanche)
            blocks_per_day = 43200  # 86400 seconds / 2 seconds per block
            blocks_7d = blocks_per_day * 7
            blocks_30d = blocks_per_day * 30
            
            # Fetch historical data
            historical_data = await self._fetch_historical_data(
                pool_contract, 
                current_block,
                blocks_7d,
                blocks_30d
            )
            
            # Calculate metrics
            metrics = await self._calculate_metrics(historical_data)
            
            logger.info(f"Historical metrics calculated: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {str(e)}")
            raise Exception(f"Error fetching historical data: {str(e)}")
            
    async def _fetch_historical_data(self, contract, current_block: int, blocks_7d: int, blocks_30d: int) -> Dict:
        """Fetch historical data points"""
        try:
            # Get data points for different time windows
            data_7d = []
            data_30d = []
            
            # Sample blocks for 7d history
            for block in range(current_block - blocks_7d, current_block, blocks_7d // 24):
                active_id = await contract.functions.getActiveId().call(block_identifier=block)
                bin_data = await contract.functions.getBin(active_id).call(block_identifier=block)
                data_7d.append({
                    'block': block,
                    'active_id': active_id,
                    'reserves': bin_data
                })
                
            # Sample blocks for 30d history
            for block in range(current_block - blocks_30d, current_block, blocks_30d // 24):
                active_id = await contract.functions.getActiveId().call(block_identifier=block)
                bin_data = await contract.functions.getBin(active_id).call(block_identifier=block)
                data_30d.append({
                    'block': block,
                    'active_id': active_id,
                    'reserves': bin_data
                })
                
            return {
                '7d': data_7d,
                '30d': data_30d
            }
            
        except Exception as e:
            logger.error(f"Error fetching historical data points: {str(e)}")
            raise
            
    async def _calculate_metrics(self, historical_data: Dict) -> HistoricalMetrics:
        """Calculate metrics from historical data"""
        try:
            # Calculate APRs
            apr_7d = self._calculate_apr(historical_data['7d'])
            apr_30d = self._calculate_apr(historical_data['30d'])
            
            # Calculate IL
            il_7d = self._calculate_impermanent_loss(historical_data['7d'])
            il_30d = self._calculate_impermanent_loss(historical_data['30d'])
            
            # Calculate volume trend
            volume_trend = self._calculate_volume_trend(historical_data['7d'])
            
            # Calculate price correlation and volatility
            price_data = self._extract_price_data(historical_data['30d'])
            volatility = self._calculate_volatility(price_data)
            correlation = self._calculate_price_correlation(price_data)
            
            # Calculate key price levels
            key_levels = self._identify_key_levels(price_data)
            
            return HistoricalMetrics(
                avg_apr_7d=apr_7d,
                avg_apr_30d=apr_30d,
                volume_trend=volume_trend,
                impermanent_loss_7d=il_7d,
                impermanent_loss_30d=il_30d,
                price_correlation=correlation,
                price_volatility=volatility,
                key_levels=key_levels
            )
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {str(e)}")
            raise