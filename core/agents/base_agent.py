from swarm import Agent, Swarm
from typing import Dict, Any
import aiohttp
from django.conf import settings
import asyncio
import requests
from datetime import datetime

class AIAgent(Agent):

    def __init__(self):
        super().__init__(
            name="Sofia",
            model="gpt-4",
            instructions="""You are a helpful assistant that provides cryptocurrency price information in multiple languages. 
            
            IMPORTANT FUNCTION USAGE RULES:
            1. ALWAYS use get_crypto_price function when ANY question involves a cryptocurrency price, regardless of language
            2. ALWAYS use calculate_crypto_amount function when ANY question involves converting amounts, regardless of language
            3. ALWAYS use get_dollar_rates function when ANY question involves Argentine dollar rates or exchanges, regardless of language

            Examples:
            - "What's the price of BTC?" -> use get_crypto_price
            - "¿Cuál es el precio de Bitcoin?" -> use get_crypto_price
            - "How much is 0.001 BTC?" -> use calculate_crypto_amount
            - "¿Cuánto valen 2 ethereum?" -> use calculate_crypto_amount
            - "¿A cuánto está el dolar blue?" -> use get_dollar_rates
        - "Cotización del dolar" -> use get_dollar_rates
            Always maintain these function calls regardless of the query language.""",
            functions=[self.get_crypto_price, self.calculate_crypto_amount, self.get_dollar_rates]
        )

    def calculate_crypto_amount(self, amount: float, symbol: str, conversion_type: str = "to_usd") -> Dict[str, Any]:
        """Calculate crypto to USD conversion or vice versa
        
        Args:
            amount (float): The amount to convert
            symbol (str): The cryptocurrency symbol or name (e.g., btc, bitcoin, eth, ethereum)
            conversion_type (str): Either 'to_usd' or 'from_usd'
        
        Returns:
            Dict with conversion result including input amount, output amount, and rate
        """
        # First get the current price
        price_data = self.get_crypto_price(symbol)
        
        if "error" in price_data:
            return price_data
            
        try:
            coin_id = list(price_data.keys())[0]
            price = price_data[coin_id]["usd"]
            
            if conversion_type == "to_usd":
                result = amount * price
                return {
                    "input_amount": amount,
                    "input_currency": symbol,
                    "output_amount": result,
                    "output_currency": "USD",
                    "rate": price
                }
            else:  # from_usd
                result = amount / price
                return {
                    "input_amount": amount,
                    "input_currency": "USD",
                    "output_amount": result,
                    "output_currency": symbol,
                    "rate": price
                }
                
        except (KeyError, IndexError, ZeroDivisionError) as e:
            return {"error": f"Failed to calculate conversion: {str(e)}"}
        
    def get_dollar_rates(self) -> Dict[str, Any]:
        """Get current Argentine dollar rates from dolarapi.com"""
        try:
            response = requests.get('https://dolarapi.com/v1/dolares')
            if response.status_code == 200:
                rates = response.json()
                return {
                    "success": True,
                    "data": rates
                }
            return {"success": False, "error": f"API returned status code {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_coin_id(self, search_term: str) -> str:
        """Search for a coin's ID using name or symbol, prioritizing popular coins"""
        headers = {
            'x-cg-demo-api-key': settings.COINGECKO_API_KEY,
            'accept': 'application/json'
        }
        
        # First check top 250 coinprs by market cap
        markets_url = "https://api.coingecko.com/api/v3/coins/markets"
        markets_params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 250,
            'page': 1,
            'sparkline': False
        }
        
        markets_response = requests.get(markets_url, headers=headers, params=markets_params)
        if markets_response.status_code == 200:
            top_coins = markets_response.json()
            search_term = search_term.lower()
            
            # First try exact matches in top coins
            for coin in top_coins:
                if (coin['symbol'].lower() == search_term or 
                    coin['id'].lower() == search_term or 
                    coin['name'].lower() == search_term):
                    return coin['id']
            
            # Then try partial matches in top coins
            for coin in top_coins:
                if (search_term in coin['symbol'].lower() or 
                    search_term in coin['id'].lower() or 
                    search_term in coin['name'].lower()):
                    return coin['id']
        
        # If not found in top coins, try the full list
        url = "https://api.coingecko.com/api/v3/coins/list"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return None
            
        coins = response.json()
        
        # Try exact matches first
        for coin in coins:
            if (coin['symbol'].lower() == search_term and 
                coin['id'] in ['bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano', 'solana']):  # Priority list
                return coin['id']
                
        for coin in coins:
            if coin['symbol'].lower() == search_term:
                return coin['id']
        
        # Finally try partial matches
        for coin in coins:
            if (search_term in coin['id'].lower() or 
                search_term in coin['symbol'].lower() or 
                search_term in coin['name'].lower()):
                return coin['id']
                
        return None

    def get_crypto_price(self, name: str) -> Dict[str, Any]:
        """Get current price of a cryptocurrency
        
        Args:
            symbol (str): The cryptocurrency symbol or name (e.g., btc, bitcoin, eth, ethereum)
        
        Returns:
            Dict with price data including USD value and 24h change
        """
        headers = {
            'x-cg-demo-api-key': settings.COINGECKO_API_KEY,
            'accept': 'application/json'
        }
        
        # First try to get the correct coin ID
        coin_id = self.get_coin_id(name)
        if not coin_id:
            return {"error": f"Could not find price for {name}"}
            
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if not result:
            return {"error": f"Could not find price for {name}"}
            
        return result

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        # Initialize context if None
        context = context or {}
        
        client = Swarm()
        
        # Check if the message is about Argentine dollars
        dollar_keywords = [
            "dolar", "dolares", "dólar", "dólares", "blue", 
            "oficial", "tarjeta", "cripto", "mayorista",
            "cuanto esta", "cuánto está", "cotización", "cotizacion",
            "precio del dolar", "precio dolar"
        ]
        
        is_dollar_query = any(keyword in message.lower() for keyword in dollar_keywords)
        
        if is_dollar_query:
            rates = self.get_dollar_rates()
            if rates["success"]:
                result = {
                    "type": "dollar_rates",
                    "data": {
                        "rates": rates["data"],
                        "timestamp": datetime.now().timestamp()
                    },
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "query": message,
                        "context": context
                    }
                }
                
                # Add a human-readable response based on the rates
                response_text = "Cotizaciones del dólar:\n"
                for rate in rates["data"]:
                    response_text += f"\n{rate['nombre']}:\n"
                    response_text += f"Compra: ${rate['compra']}\n"
                    response_text += f"Venta: ${rate['venta']}\n"
                
                result["response"] = response_text
                return result
        
        # Add context to the messages if provided
        messages = [{"role": "user", "content": message}]
        if context:
            # Add context as system message
            context_message = "Context information:\n"
            for key, value in context.items():
                context_message += f"- {key}: {value}\n"
            messages.insert(0, {"role": "system", "content": context_message})
        
        response = client.run(
            agent=self,
            messages=messages
        )

        # Common crypto symbols and their variations
        crypto_symbols = {
            "btc": ["btc", "bitcoin", "btcs", "xbt", "bitcoins", "бтк"],
            "eth": ["eth", "ethereum", "ether", "ethereums", "етх"],
            "sol": ["sol", "solana", "sols", "солана"],
            "usdt": ["usdt", "tether", "тезер"],
            "bnb": ["bnb", "binance", "binance coin", "binancecoin"],
            "ada": ["ada", "cardano", "кардано"],
            "xrp": ["xrp", "ripple", "рипл"],
            "doge": ["doge", "dogecoin", "догекоин"],
            # Add more as needed
        }
        
        result = {
            "response": response.messages[-1]["content"],
            "type": "general",
            "data": {},
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "query": message,
                "context": context  # Include the context in metadata
            }
        }

        # Extract numbers and symbols from message
        message_words = message.lower().split()
        found_numbers = []
        found_symbol = None

        # Find crypto symbol
        for word in message_words:
            for main_symbol, variations in crypto_symbols.items():
                if word in variations:
                    found_symbol = main_symbol
                    break
            if found_symbol:
                break

        # Find numbers (including decimals)
        for word in message_words:
            # Remove common thousand separators and convert decimal separators
            cleaned_word = word.replace(',', '').replace(' ', '')
            try:
                # Try parsing as float (handles both . and , as decimal separator)
                if '.' in cleaned_word:
                    number = float(cleaned_word)
                elif ',' in cleaned_word:
                    number = float(cleaned_word.replace(',', '.'))
                else:
                    number = float(cleaned_word)
                found_numbers.append(number)
            except ValueError:
                continue

        # If we found a crypto symbol, it's either a price query or conversion
        if found_symbol:
            price_data = self.get_crypto_price(found_symbol)
            if price_data and not "error" in price_data:
                coin_id = list(price_data.keys())[0]
                current_price = price_data[coin_id]["usd"]
                
                # If we found numbers, it's likely a conversion query
                if found_numbers:
                    amount = found_numbers[0]
                    conversion = self.calculate_crypto_amount(amount, found_symbol)
                    if conversion and not "error" in conversion:
                        result.update({
                            "type": "conversion_query",
                            "data": {
                                "input_amount": conversion["input_amount"],
                                "input_currency": conversion["input_currency"],
                                "output_amount": conversion["output_amount"],
                                "output_currency": conversion["output_currency"],
                                "rate": conversion["rate"],
                                "timestamp": datetime.now().timestamp()
                            }
                        })
                # If no numbers, it's likely a price query
                else:
                    result.update({
                        "type": "price_query",
                        "data": {
                            "price_usd": current_price,
                            "price_change_24h": price_data[coin_id].get("usd_24h_change"),
                            "symbol": found_symbol,
                            "coin_id": coin_id,
                            "timestamp": datetime.now().timestamp()
                        }
                    })

        return result