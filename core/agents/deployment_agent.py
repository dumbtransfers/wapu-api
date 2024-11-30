import logging
from swarm import Agent
from typing import Dict, Any, Optional
from django.conf import settings
from pydantic import Field, ConfigDict
from swarm import Swarm

logger = logging.getLogger(__name__)

class DeploymentAgent(Agent):
    def __init__(self):
        logger.info("="*50)
        logger.info("INITIALIZING DEPLOYMENT AGENT")
        logger.info("="*50)
        
        super().__init__(
            name="Deployment Assistant",
            model="gpt-4",
            instructions="""You are a deployment assistant that helps users deploy ERC-20 tokens through natural conversation.
            
            Your task is to analyze messages and context to identify token deployment parameters:
            1. name: The token's full name
            2. symbol: The token's ticker symbol (usually 3-4 characters)
            3. total_supply: The total supply of tokens (default: 1,000,000)
            4. logo: A token logo image is required before deployment
            
            IMPORTANT:
            - Users may write in any language
            - CAREFULLY analyze the entire conversation history to find previously provided parameters
            - Do not ask for information that was already provided in the conversation
            - When all parameters (name, symbol, supply, logo) are found in the context, proceed with deployment
            - If user asks to deploy and all parameters are present, use prepare_token_deployment
            - Only ask for missing parameters that haven't been mentioned in the conversation
            
            ALWAYS use the extract_token_parameters function to specify found parameters.
            Include reasoning about why you identified each parameter.""",
            functions=[self.extract_token_parameters, self.prepare_token_deployment]
        )

    async def extract_token_parameters(
        self,
        name: Optional[str] = None,
        symbol: Optional[str] = None,
        total_supply: Optional[int] = None,
        logo_url: Optional[str] = None,
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """Extract token parameters from message and context
        
        Args:
            name: Token name if found
            symbol: Token symbol if found
            total_supply: Total supply if found
            logo_url: URL of the token logo if found
            reasoning: Explanation of parameter extraction
        """
        return {
            "parameters": {
                "name": name,
                "symbol": symbol,
                "total_supply": total_supply,
                "logo_url": logo_url
            },
            "reasoning": reasoning
        }

    async def process_message(self, message: str, context: Dict = None) -> Dict[str, Any]:
        """Process deployment requests using Swarm's AI capabilities"""
        try:
            # Initialize context variables
            context_variables = context or {}
            deployment_params = {}
            
            # Get conversation history
            conversation_history = context_variables.get('history', [])
            
            # Process conversation history
            formatted_history = []
            for item in conversation_history:
                role = item.get('role')
                content = item.get('content')
                
                if content.startswith('http') and ('png' in content or 'jpg' in content):
                    deployment_params["logo_url"] = content
                    formatted_history.append(f"{role}: <image_url>")
                else:
                    formatted_history.append(f"{role}: {content}")

            # Build the full conversation context
            full_conversation = "\n".join(formatted_history)
            
            logger.info(f"Processing full conversation:\n{full_conversation}")
            
            # Analyze message and context with AI
            client = Swarm()
            response = client.run(
                agent=self,
                messages=[{
                "role": "system",
                "content": "You are analyzing a conversation to extract token deployment parameters. The conversation history is provided in chronological order."
            }, {
                "role": "user",
                "content": f"""Previous conversation:
{full_conversation}

Current message:
{message}"""
                }]
            )

            # Extract parameters from AI response
            tool_calls = response.messages[0].get('tool_calls', [])
            if tool_calls and tool_calls[0]['type'] == 'function':
                try:
                    import json
                    args = json.loads(tool_calls[0]['function']['arguments'])
                    
                    # Update deployment params with all found parameters
                    if args.get("name"):
                        deployment_params["name"] = args["name"]
                    if args.get("symbol"):
                        deployment_params["symbol"] = args["symbol"]
                    if args.get("total_supply"):
                        deployment_params["total_supply"] = int(args["total_supply"])

                    # If we have all required parameters, proceed with deployment
                    if all(key in deployment_params for key in ["name", "symbol", "logo_url"]):
                        deployment_data = await self.prepare_token_deployment(
                            name=deployment_params["name"],
                            symbol=deployment_params["symbol"],
                            total_supply=deployment_params.get("total_supply", 1_000_000),
                            logo_url=deployment_params["logo_url"]
                        )
                        return {
                            "response": deployment_data,
                            "routing": {
                                "agent": "deployment",
                                "confidence": 1.0
                            }
                        }
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing AI response: {str(e)}")
                    return {"error": "Invalid response format from AI"}

            # If we get here, something is missing
            next_prompt = await self.generate_next_prompt(deployment_params)
            return {
                "response": next_prompt,
                "routing": {
                    "agent": "deployment",
                    "confidence": 1.0
                }
            }

        except Exception as e:
            logger.error(f"Error processing deployment message: {str(e)}")
            return {"error": str(e)}

    async def generate_next_prompt(self, collected_params: Dict[str, Any]) -> str:
        """Generate appropriate next message based on missing parameters"""
        client = Swarm()
        response = client.run(
            agent=self,
            messages=[{
                "role": "system",
                "content": f"""Current parameters: {collected_params}
                Generate a natural response asking for missing required parameters (name, symbol, total_supply).
                If all parameters are collected, ask for confirmation."""
            }]
        )
        return response.messages[-1]["content"]

    async def prepare_token_deployment(self, 
        name: str,
        symbol: str,
        total_supply: int = 1_000_000,
        decimals: int = 18,
        logo_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepare ERC-20 token deployment data for frontend"""
        try:
            client = Swarm()
            
            # Check if we have a logo
            if not logo_url:
                return {
                    "type": "needs_image",
                    "message": f"Great! I have all the token details. Now we just need a logo for your {name} token. Would you like me to generate one for you?",
                    "deployment_params": {
                        "name": name,
                        "symbol": symbol,
                        "total_supply": total_supply
                    }
                }
            
            # Let AI generate the confirmation message
            response = client.run(
                agent=self,
                messages=[{
                    "role": "system", 
                    "content": "Generate a friendly confirmation message for token deployment. Include all parameters and ask for confirmation."
                }, {
                    "role": "user",
                    "content": f"Generate deployment confirmation for: Name={name}, Symbol={symbol}, Total Supply={total_supply}, Decimals={decimals}, Logo=Yes"
                }]
            )
            
            ai_message = response.messages[-1]["content"]
            
            return {
                "type": "deployment_ready",
                "network": {
                    "name": "unichain",
                    "rpc_url": "https://sepolia.unichain.org",
                    "chain_id": "222"
                },
                "contract_data": {
                    "abi": [
                        {
                            "inputs": [],
                            "stateMutability": "nonpayable",
                            "type": "constructor"
                        },
                        {
                            "inputs": [
                                {
                                    "internalType": "string",
                                    "name": "_name",
                                    "type": "string"
                                },
                                {
                                    "internalType": "string",
                                    "name": "_symbol",
                                    "type": "string"
                                },
                                {
                                    "internalType": "uint8",
                                    "name": "_decimals",
                                    "type": "uint8"
                                }
                            ],
                            "stateMutability": "nonpayable",
                            "type": "constructor"
                        }
                    ],
                    "bytecode": "60806040526040518060400160405280600a81526020017f44656d6f20546f6b656e000000000000000000000000000000000000000000008152505f9081610047919061035e565b506040518060400160405280600381526020017f444d5400000000000000000000000000000000000000000000000000000000008152506001908161008c919061035e565b50601260025f6101000a81548160ff021916908360ff1602179055503480156100b3575f80fd5b506040516110c53803806110c583398181016040528101906100d5919061045b565b806003819055508060045f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f208190555050610486565b5f81519050919050565b7f4e487b71000000000000000000000000000000000000000000000000000000005f52604160045260245ffd5b7f4e487b71000000000000000000000000000000000000000000000000000000005f52602260045260245ffd5b5f600282049050600182168061019f57607f821691505b6020821081036101b2576101b161015b565b5b50919050565b5f819050815f5260205f209050919050565b5f6020601f8301049050919050565b5f82821b905092915050565b5f600883026102147fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff826101d9565b61021e86836101d9565b95508019841693508086168417925050509392505050565b5f819050919050565b5f819050919050565b5f61026261025d61025884610236565b61023f565b610236565b9050919050565b5f819050919050565b61027b83610248565b61028f61028782610269565b8484546101e5565b825550505050565b5f90565b6102a3610297565b6102ae818484610272565b505050565b5b818110156102d1576102c65f8261029b565b6001810190506102b4565b5050565b601f821115610316576102e7816101b8565b6102f0846101ca565b810160208510156102ff578190505b61031361030b856101ca565b8301826102b3565b50505b505050565b5f82821c905092915050565b5f6103365f198460080261031b565b1980831691505092915050565b5f61034e8383610327565b9150826002028217905092915050565b61036782610124565b67ffffffffffffffff8111156103805761037f61012e565b5b61038a8254610188565b6103958282856102d5565b5f60209050601f8311600181146103c6575f84156103b4578287015190505b6103be8582610343565b865550610425565b601f1984166103d4866101b8565b5f5b828110156103fb578489015182556001820191506020850194506020810190506103d6565b868310156104185784890151610414601f891682610327565b8355505b6001600288020188555050505b505050505050565b5f80fd5b61043a81610236565b8114610444575f80fd5b50565b5f8151905061045581610431565b92915050565b5f602082840312156104705761046f61042d565b5b5f61047d84828501610447565b91505092915050565b610c32806104935f395ff3fe608060405234801561000f575f80fd5b5060043610610091575f3560e01c8063313ce56711610064578063313ce5671461013157806370a082311461014f57806395d89b411461017f578063a9059cbb1461019d578063dd62ed3e146101cd57610091565b806306fdde0314610095578063095ea7b3146100b357806318160ddd146100e357806323b872dd14610101575b5f80fd5b61009d6101fd565b6040516100aa9190610805565b60405180910390f35b6100cd60048036038101906100c891906108b6565b610288565b6040516100da919061090e565b60405180910390f35b6100eb610310565b6040516100f89190610936565b60405180910390f35b61011b6004803603810190610116919061094f565b610316565b604051610128919061090e565b60405180910390f35b610139610591565b60405161014691906109ba565b60405180910390f35b610169600480360381019061016491906109d3565b6105a3565b6040516101769190610936565b60405180910390f35b6101876105b8565b6040516101949190610805565b60405180910390f35b6101b760048036038101906101b291906108b6565b610644565b6040516101c4919061090e565b60405180910390f35b6101e760048036038101906101e291906109fe565b610775565b6040516101f49190610936565b60405180910390f35b5f805461020990610a69565b80601f016020809104026020016040519081016040528092919081815260200182805461023590610a69565b80156102805780601f1061025757610100808354040283529160200191610280565b820191905f5260205f20905b81548152906001019060200180831161026357829003601f168201915b505050505081565b5f8160055f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f20819055506001905092915050565b60035481565b5f8160045f8673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f20541015610397576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161038e90610ae3565b60405180910390fd5b8160055f8673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f20541015610452576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161044990610b4b565b60405180910390fd5b8160045f8673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f82825461049e9190610b96565b925050819055508160045f8573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8282546104f19190610bc9565b925050819055508160055f8673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f82825461057f9190610b96565b92505081905550600190509392505050565b60025f9054906101000a900460ff1681565b6004602052805f5260405f205f915090505481565b600180546105c590610a69565b80601f01602080910402602001604051908101604052809291908181526020018280546105f190610a69565b801561063c5780601f106106135761010080835404028352916020019161063c565b820191905f5260205f20905b81548152906001019060200180831161061f57829003601f168201915b505050505081565b5f8160045f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205410156106c5576040517f08c379a00000000000000000000000000000000000000000000000000000000081526004016106bc90610ae3565b60405180910390fd5b8160045f3373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8282546107119190610b96565b925050819055508160045f8573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020015f205f8282546107649190610bc9565b925050819055506001905092915050565b6005602052815f5260405f20602052805f5260405f205f91509150505481565b5f81519050919050565b5f82825260208201905092915050565b8281835e5f83830152505050565b5f601f19601f8301169050919050565b5f6107d782610795565b6107e1818561079f565b93506107f18185602086016107af565b6107fa816107bd565b840191505092915050565b5f6020820190508181035f83015261081d81846107cd565b905092915050565b5f80fd5b5f73ffffffffffffffffffffffffffffffffffffffff82169050919050565b5f61085282610829565b9050919050565b61086281610848565b811461086c575f80fd5b50565b5f8135905061087d81610859565b92915050565b5f819050919050565b61089581610883565b811461089f575f80fd5b50565b5f813590506108b08161088c565b92915050565b5f80604083850312156108cc576108cb610825565b5b5f6108d98582860161086f565b92505060206108ea858286016108a2565b9150509250929050565b5f8115159050919050565b610908816108f4565b82525050565b5f6020820190506109215f8301846108ff565b92915050565b61093081610883565b82525050565b5f6020820190506109495f830184610927565b92915050565b5f805f6060848603121561096657610965610825565b5b5f6109738682870161086f565b93505060206109848682870161086f565b9250506040610995868287016108a2565b9150509250925092565b5f60ff82169050919050565b6109b48161099f565b82525050565b5f6020820190506109cd5f8301846109ab565b92915050565b5f602082840312156109e8576109e7610825565b5b5f6109f58482850161086f565b91505092915050565b5f8060408385031215610a1457610a13610825565b5b5f610a218582860161086f565b9250506020610a328582860161086f565b9150509250929050565b7f4e487b71000000000000000000000000000000000000000000000000000000005f52602260045260245ffd5b5f6002820490506001821680610a8057607f821691505b602082108103610a9357610a92610a3c565b5b50919050565b7f496e73756666696369656e742062616c616e63650000000000000000000000005f82015250565b5f610acd60148361079f565b9150610ad882610a99565b602082019050919050565b5f6020820190508181035f830152610afa81610ac1565b9050919050565b7f416c6c6f77616e636520657863656564656400000000000000000000000000005f82015250565b5f610b3560128361079f565b9150610b4082610b01565b602082019050919050565b5f6020820190508181035f830152610b6281610b29565b9050919050565b7f4e487b71000000000000000000000000000000000000000000000000000000005f52601160045260245ffd5b5f610ba082610883565b9150610bab83610883565b9250828203905081811115610bc357610bc2610b69565b5b92915050565b5f610bd382610883565b9150610bde83610883565b9250828201905080821115610bf657610bf5610b69565b5b9291505056fea2646970667358221220c951b57c41e744a805eae330bbf55683422d56524f8f02ee28f064b2c283b8f864736f6c634300081a0033"
                },
                "constructor_args": [name, symbol, decimals],
                "deployment_params": {
                    "name": name,
                    "symbol": symbol,
                    "decimals": decimals,
                    "total_supply": total_supply,
                    "logo_url": logo_url
                },
                "message": ai_message
            }
        except Exception as e:
            logger.error(f"Error preparing token deployment: {str(e)}")
            return {"error": str(e)}