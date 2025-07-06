import asyncio
import time
from decimal import Decimal

from eth_typing import ChecksumAddress
from web3 import Account, AsyncHTTPProvider, AsyncWeb3
from web3.contract.async_contract import AsyncContract
from web3.types import TxParams

from .constant import (
    ERC20_ABI,
    PANCAKESSWAP_CONTRACT_V2_FACTORY,
    PANCAKESSWAP_CONTRACT_V2_FACTORY_ABI,
    PANCAKESSWAP_CONTRACT_V2_ROUTER,
    PANCAKESSWAP_CONTRACT_V2_ROUTER_ABI,
    PANCAKESSWAP_CONTRACT_V2_PAIR_ABI,
)


class PancakeSwapV2:
    """PancakeSwap V2 SDK for interacting with PancakeSwap decentralized exchange.

    This class provides methods for liquidity management, token swapping, and other
    DeFi operations on the Binance Smart Chain using PancakeSwap V2 protocol.
    """

    def __init__(self, json_rpc: str, private_key: str, gas_several: float = 1.1) -> None:
        """Initialize the PancakeSwap V2 SDK.

        Args:
            json_rpc (str): The JSON-RPC endpoint URL for connecting to BSC network.
            private_key (str): The private key of the wallet account for transactions.
            gas_several (float, optional): Gas price multiplier for transaction speed.
                Defaults to 1.1.

        Returns:
            None
        """
        self.w3 = AsyncWeb3(AsyncHTTPProvider(json_rpc))
        self.account = Account.from_key(private_key)
        self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT = self.w3.eth.contract(PANCAKESSWAP_CONTRACT_V2_ROUTER, abi=PANCAKESSWAP_CONTRACT_V2_ROUTER_ABI)
        self.PANCAKESSWAP_CONTRACT_V2_FACTORY_CONTRACT = self.w3.eth.contract(PANCAKESSWAP_CONTRACT_V2_FACTORY, abi=PANCAKESSWAP_CONTRACT_V2_FACTORY_ABI)
        self.MAX_UINT256 = 2**256 - 1
        self.gas_several = gas_several
        self.ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

    def _get_checksum_address(self, address: str) -> ChecksumAddress:
        """Convert an address string to a valid checksum address.

        Args:
            address (str): The address string to convert.

        Returns:
            ChecksumAddress: The checksummed address.
        """
        return self.w3.to_checksum_address(address)

    def _get_contract(self, token_address: str) -> AsyncContract:
        """Create an ERC20 contract instance for the given token address.

        Args:
            token_address (str): The address of the ERC20 token contract.

        Returns:
            AsyncContract: The contract instance for the token.
        """
        return self.w3.eth.contract(
            self._get_checksum_address(token_address),
            abi=ERC20_ABI,
        )

    async def _token_decimal(self, token_address: str) -> int:
        """Get the decimal places of a token.

        Args:
            token_address (str): The address of the token contract.

        Returns:
            int: The number of decimal places for the token.
        """
        token_contract = self._get_contract(token_address)
        decimals = await token_contract.functions.decimals().call()
        return int(decimals)

    async def _token_allowance(self, token_address: str, from_address: str, recipient: str) -> int:
        """Check the allowance amount for a token between two addresses.

        Args:
            token_address (str): The address of the token contract.
            from_address (str): The address of the token owner.
            recipient (str): The address of the spender.

        Returns:
            int: The allowance amount in wei.
        """
        token_contract = self._get_contract(token_address)
        allowance = await token_contract.functions.allowance(
            self._get_checksum_address(from_address),
            self._get_checksum_address(recipient),
        ).call()
        return int(allowance)

    async def _token_approve(self, token_address: str, guy_address: str) -> str:
        """Approve maximum allowance for a token to a spender address.

        Args:
            token_address (str): The address of the token contract.
            guy_address (str): The address to approve spending rights to.

        Returns:
            str: The transaction hash of the approval transaction.
        """
        guy_addr = self._get_checksum_address(guy_address)
        token_contract = self._get_contract(token_address)  # self.MAX_UINT256
        transaction = await token_contract.functions.approve(guy_addr, self.MAX_UINT256).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def _approve_check(self, token_address: str, check_amount: int | float) -> str | None:
        """Check if approval is needed and approve if insufficient allowance.

        Args:
            token_address (str): The address of the token contract.
            check_amount (int | float): The amount to check allowance against.

        Returns:
            str | None: The transaction hash if approval was needed, None otherwise.
        """
        allowance = await self._token_allowance(
            token_address=token_address,
            from_address=self.account.address,
            recipient=self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.address,
        )
        if allowance and allowance > check_amount:
            ...
        else:
            return await self._token_approve(
                token_address=token_address,
                guy_address=self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.address,
            )

    async def _build_base_tx(self) -> TxParams:
        """Build base transaction parameters with gas price and sender address.

        Returns:
            TxParams: The base transaction parameters dictionary.
        """
        tx_params: TxParams = {
            "from": self.account.address,
            "gasPrice": self.w3.to_wei((await self.w3.eth.gas_price).numerator * self.gas_several, "wei"),
        }
        return tx_params

    async def _send_transaction(self, transaction: TxParams) -> str:
        """Sign and send a transaction to the blockchain.

        Args:
            transaction (TxParams): The transaction parameters to send.

        Returns:
            str: The transaction hash of the sent transaction.
        """
        if "from" in transaction:
            from_address = self.w3.to_checksum_address(transaction["from"])
            transaction["nonce"] = await self.w3.eth.get_transaction_count(from_address)
        transaction["gas"] = int((await self.w3.eth.estimate_gas(transaction)) * self.gas_several)
        signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key=self.account.key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_receipt.get("transactionHash").hex()

    async def get_pair(self, tokenA: str, tokenB: str) -> ChecksumAddress:
        """Get the pair address for two tokens from the factory contract.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.

        Returns:
            ChecksumAddress: The address of the liquidity pair contract.
        """
        pair = await self.PANCAKESSWAP_CONTRACT_V2_FACTORY_CONTRACT.functions.getPair(
            self._get_checksum_address(tokenA),
            self._get_checksum_address(tokenB),
        ).call()
        return self._get_checksum_address(pair)

    async def auto_create_pair(self, tokenA: str, tokenB: str) -> str:
        """Create a new liquidity pair for two tokens if it doesn't exist.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.

        Returns:
            str: transaction hash.
        """
        transaction = await self.PANCAKESSWAP_CONTRACT_V2_FACTORY_CONTRACT.functions.createPair(
            self._get_checksum_address(tokenA),
            self._get_checksum_address(tokenB),
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def get_reserves(self, tokenA: str, tokenB: str):
        """Get the reserves of both tokens in a liquidity pair.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.

        Returns:
            tuple: A tuple containing (reserveA, reserveB, block_timestamp_last).
                Returns (0, 0, 0) if the pair doesn't exist.
        """
        pair_address = await self.get_pair(tokenA, tokenB)
        if pair_address == self.ZERO_ADDRESS:
            return 0, 0, 0

        pair_contract = self.w3.eth.contract(pair_address, abi=PANCAKESSWAP_CONTRACT_V2_PAIR_ABI)  # 需要添加Pair合约的ABI
        reserves, token0 = await asyncio.gather(
            pair_contract.functions.getReserves().call(),
            pair_contract.functions.token0().call(),
        )
        if token0.lower() == tokenA.lower():
            return reserves[0], reserves[1], reserves[2]
        else:
            return reserves[1], reserves[0], reserves[2]

    async def _adjust_liquidity_amounts(
        self,
        tokenA: str,
        tokenB: str,
        amountA: int,
        amountB: int,
    ) -> tuple[int, int]:
        """Adjust liquidity amounts to maintain the current pool ratio.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (int): The desired amount of tokenA.
            amountB (int): The desired amount of tokenB.

        Returns:
            tuple[int, int]: The adjusted amounts (amountA_adjusted, amountB_adjusted).
        """
        reserveA, reserveB, _ = await self.get_reserves(tokenA, tokenB)
        if reserveA == 0 or reserveB == 0:
            return amountA, amountB

        amountB_optimal = await self._quote(amountA, reserveA, reserveB)
        if amountB_optimal <= amountB:
            return amountA, amountB_optimal
        else:
            amountA_optimal = await self._quote(amountB, reserveB, reserveA)
            return amountA_optimal, amountB

    async def _quote(self, amountA: int, reserveA: int, reserveB: int) -> int:
        """Calculate the equivalent amount of tokenB for a given amount of tokenA.

        Args:
            amountA (int): The amount of tokenA.
            reserveA (int): The reserve amount of tokenA in the pool.
            reserveB (int): The reserve amount of tokenB in the pool.

        Returns:
            int: The equivalent amount of tokenB.

        Raises:
            ValueError: If amountA is zero or reserves are zero.
        """
        if amountA == 0:
            raise ValueError("amountA cannot be zero.")
        if reserveA == 0 or reserveB == 0:
            raise ValueError("The reserve quantity cannot be zero")
        return (amountA * reserveB) // reserveA

    async def auto_create_liquidity(
        self,
        tokenA: str,
        tokenB: str,
        amountA: int | float,
        amountB: int | float,
        slippage: float = 0.05,
    ) -> str:
        """Create liquidity for a new token pair.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (int | float): The amount of tokenA to add as liquidity.
            amountB (int | float): The amount of tokenB to add as liquidity.
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).

        Returns:
            str: The transaction hash of the liquidity creation transaction.
        """
        await asyncio.gather(
            self._approve_check(token_address=tokenA, check_amount=amountA),
            self._approve_check(token_address=tokenB, check_amount=amountB),
        )

        token_A = self._get_checksum_address(tokenA)
        token_B = self._get_checksum_address(tokenB)

        token_A_decimal, token_B_decimal = await asyncio.gather(
            self._token_decimal(tokenA),
            self._token_decimal(tokenA),
        )
        amount_A_desired = int(Decimal(f"1e{str(token_A_decimal)}") * Decimal(str(amountA)))
        amount_B_desired = int(Decimal(f"1e{str(token_B_decimal)}") * Decimal(str(amountB)))

        amount_A_Min = int(Decimal(str(amount_A_desired)) * Decimal(str(1 - slippage)))
        amount_B_Min = int(Decimal(str(amount_B_desired)) * Decimal(str(1 - slippage)))

        recipient = self.account.address
        deadline = int(time.time()) + 60 * 100

        transaction = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.addLiquidity(
            token_A,
            token_B,
            amount_A_desired,
            amount_B_desired,
            amount_A_Min,
            amount_B_Min,
            recipient,
            deadline,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_increase_liquidity(
        self,
        tokenA: str,
        tokenB: str,
        amountA: int | float,
        amountB: int | float,
        slippage: float = 0.05,
        auto_adjust: bool = True,
    ) -> str:
        """Add liquidity to an existing token pair.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (int | float): The amount of tokenA to add as liquidity.
            amountB (int | float): The amount of tokenB to add as liquidity.
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).
            auto_adjust (bool, optional): Whether to automatically adjust amounts to match
                pool ratio. Defaults to True.

        Returns:
            str: The transaction hash of the liquidity addition transaction.
        """
        await asyncio.gather(
            self._approve_check(token_address=tokenA, check_amount=amountA),
            self._approve_check(token_address=tokenB, check_amount=amountB),
        )

        token_A = self._get_checksum_address(tokenA)
        token_B = self._get_checksum_address(tokenB)

        token_A_decimal, token_B_decimal = await asyncio.gather(
            self._token_decimal(tokenA),
            self._token_decimal(tokenA),
        )
        amount_A_desired = int(Decimal(f"1e{str(token_A_decimal)}") * Decimal(str(amountA)))
        amount_B_desired = int(Decimal(f"1e{str(token_B_decimal)}") * Decimal(str(amountB)))

        if auto_adjust:
            amount_A_desired, amount_B_desired = await self._adjust_liquidity_amounts(
                token_A,
                token_B,
                amount_A_desired,
                amount_B_desired,
            )

        amount_A_Min = int(Decimal(str(amount_A_desired)) * Decimal(str(1 - slippage)))
        amount_B_Min = int(Decimal(str(amount_B_desired)) * Decimal(str(1 - slippage)))

        recipient = self.account.address
        deadline = int(time.time()) + 60 * 100

        transaction = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.addLiquidity(
            token_A,
            token_B,
            amount_A_desired,
            amount_B_desired,
            amount_A_Min,
            amount_B_Min,
            recipient,
            deadline,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_decrease_liquidity(
        self,
        tokenA: str,
        tokenB: str,
        liquidity_percentage: int | float,
        slippage: float = 0.05,
    ) -> str:
        """Remove liquidity from a token pair.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            liquidity_percentage (int | float): The percentage of liquidity to remove (0-1).
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).

        Returns:
            str: The transaction hash of the liquidity removal transaction.

        Raises:
            ValueError: If liquidity_percentage is greater than 1 or if the pair doesn't exist.
        """
        if liquidity_percentage > 1:
            raise ValueError("liquidity_percentage cannot be greater than 1.")

        token_A = self._get_checksum_address(tokenA)
        token_B = self._get_checksum_address(tokenB)
        recipient = self.account.address
        deadline = int(time.time()) + 60 * 100

        pair_address = await self.get_pair(tokenA, tokenB)
        if pair_address == self.ZERO_ADDRESS:
            raise ValueError(f" The trading pair does not exist: {tokenA} - {tokenB}")

        lp_balance = await self.get_lp_balance(pair_address)
        liquidity_wei = int(Decimal(str(lp_balance)) * Decimal(str(liquidity_percentage)))
        reserveA, reserveB, _ = await self.get_reserves(tokenA, tokenB)
        total_supply = await self.get_lp_total_supply(pair_address)

        expected_amountA = (liquidity_wei * reserveA) // total_supply
        expected_amountB = (liquidity_wei * reserveB) // total_supply

        amountA_min = int(Decimal(str(expected_amountA)) * Decimal(str(1 - slippage)))
        amountB_min = int(Decimal(str(expected_amountB)) * Decimal(str(1 - slippage)))

        await self._approve_check(token_address=pair_address, check_amount=liquidity_wei)
        transaction = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.removeLiquidity(
            token_A,
            token_B,
            liquidity_wei,
            amountA_min,
            amountB_min,
            recipient,
            deadline,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def get_lp_balance(self, pair_address: str) -> int:
        """Get the LP token balance for the current account.

        Args:
            pair_address (str): The address of the liquidity pair contract.

        Returns:
            int: The LP token balance in wei.
        """
        pair_addr = self._get_checksum_address(pair_address)
        pair_contract = self.w3.eth.contract(pair_addr, abi=PANCAKESSWAP_CONTRACT_V2_PAIR_ABI)
        balance = await pair_contract.functions.balanceOf(self.account.address).call()
        return int(balance)

    async def get_lp_total_supply(self, pair_address: str) -> int:
        """Get the total supply of LP tokens for a pair.

        Args:
            pair_address (str): The address of the liquidity pair contract.

        Returns:
            int: The total supply of LP tokens in wei.
        """
        pair_addr = self._get_checksum_address(pair_address)
        pair_contract = self.w3.eth.contract(pair_addr, abi=PANCAKESSWAP_CONTRACT_V2_PAIR_ABI)
        total_supply = await pair_contract.functions.totalSupply().call()
        return int(total_supply)

    async def get_amounts_out(self, tokenA: str, tokenB: str, tokenAmountIn: int | float) -> float:
        """Calculate the output amount for a given input amount in a swap.

        Args:
            tokenA (str): The address of the input token.
            tokenB (str): The address of the output token.
            tokenAmountIn (int | float): The amount of input tokens.

        Returns:
            float: The expected output amount of tokenB.
        """
        amount_in = int(Decimal(f"1e{await self._token_decimal(tokenA)}") * Decimal(str(tokenAmountIn)))
        amounts = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.getAmountsOut(
            amount_in,
            [tokenA, tokenB],
        ).call()

        return float(Decimal(str(amounts[-1])) / Decimal(f"1e{await self._token_decimal(tokenB)}"))

    async def get_amounts_in(self, tokenA: str, tokenB: str, tokenAmountOut: int | float) -> float:
        """Calculate the input amount needed for a desired output amount in a swap.

        Args:
            tokenA (str): The address of the input token.
            tokenB (str): The address of the output token.
            tokenAmountOut (int | float): The desired amount of output tokens.

        Returns:
            float: The required input amount of tokenA.
        """
        amount_out = int(Decimal(f"1e{await self._token_decimal(tokenB)}") * Decimal(str(tokenAmountOut)))
        amounts = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.getAmountsIn(
            amount_out,
            [tokenA, tokenB],
        ).call()
        return float(Decimal(str(amounts[0])) / Decimal(f"1e{await self._token_decimal(tokenA)}"))

    async def get_optimal_path(self, tokenIn: str, tokenOut: str) -> list[ChecksumAddress]:
        """Get the optimal swap path between two tokens.

        Args:
            tokenIn (str): The address of the input token.
            tokenOut (str): The address of the output token.

        Returns:
            list[ChecksumAddress]: The optimal path for the swap. Returns direct path
                if pair exists, otherwise uses WBNB as intermediate token.
        """
        token_in = self._get_checksum_address(tokenIn)
        token_out = self._get_checksum_address(tokenOut)

        pair_address = await self.PANCAKESSWAP_CONTRACT_V2_FACTORY_CONTRACT.functions.getPair(
            token_in,
            token_out,
        ).call()
        if pair_address != self.ZERO_ADDRESS:
            return [token_in, token_out]

        wbnb_address = await self.WETH()
        if token_in.lower() == wbnb_address.lower():
            return [token_in, token_out]
        elif token_out.lower() == wbnb_address.lower():
            return [token_in, token_out]

        return [token_in, wbnb_address, token_out]

    async def auto_swap(
        self,
        tokenIn: str,
        tokenOut: str,
        amountIn: int | float,
        slippage: float = 0.05,
    ) -> str:
        """Swap exact input tokens for output tokens with slippage protection.

        Args:
            tokenIn (str): The address of the input token.
            tokenOut (str): The address of the output token.
            amountIn (int | float): The amount of input tokens to swap.
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).

        Returns:
            str: The transaction hash of the swap transaction.
        """
        token_in = self._get_checksum_address(tokenIn)
        token_out = self._get_checksum_address(tokenOut)
        recipient = self.account.address
        deadline = int(time.time()) + 60 * 100

        amount_in_wei = int(Decimal(f"1e{str(await self._token_decimal(token_in))}") * Decimal(str(amountIn)))
        path = await self.get_optimal_path(token_in, token_out)

        amounts_out = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.getAmountsOut(
            amount_in_wei,
            path,
        ).call()
        amount_out_min = int(Decimal(str(amounts_out[-1])) * Decimal(str(1 - slippage)))
        await self._approve_check(token_address=token_in, check_amount=amount_in_wei)
        transaction = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.swapExactTokensForTokens(
            amount_in_wei,
            amount_out_min,
            path,
            recipient,
            deadline,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def WETH(self) -> ChecksumAddress:
        """Get the WETH (Wrapped BNB) address from the router contract.

        Returns:
            ChecksumAddress: The address of the WETH contract.
        """
        weth_address = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.WETH().call()
        return self._get_checksum_address(weth_address)

    async def factory(self) -> ChecksumAddress:
        """Get the factory contract address from the router contract.

        Returns:
            ChecksumAddress: The address of the PancakeSwap factory contract.
        """
        factory_address = await self.PANCAKESSWAP_CONTRACT_V2_ROUTER_CONTRACT.functions.factory().call()
        return self._get_checksum_address(factory_address)

    async def wrap_bnb(self, amount_bnb: int | float) -> str:
        """Wrap BNB to WBNB tokens.

        Args:
            amount_bnb (int | float): The amount of BNB to wrap in ether units.

        Returns:
            str: The transaction hash of the wrapping transaction.
        """
        wbnb_contract = self.w3.eth.contract(await self.WETH(), abi=ERC20_ABI)
        base_tx = await self._build_base_tx()
        base_tx["value"] = self.w3.to_wei(amount_bnb, "ether")
        transaction = await wbnb_contract.functions.deposit().build_transaction(base_tx)
        return await self._send_transaction(transaction)

    async def unwrap_wbnb(self, amount_wbnb: int | float) -> str:
        """Unwrap WBNB tokens back to BNB.

        Args:
            amount_wbnb (int | float): The amount of WBNB to unwrap in ether units.

        Returns:
            str: The transaction hash of the unwrapping transaction.
        """
        amount = self.w3.to_wei(amount_wbnb, "ether")
        wbnb_contract = self.w3.eth.contract(await self.WETH(), abi=ERC20_ABI)
        transaction = await wbnb_contract.functions.withdraw(amount).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    def get_account_address(self) -> str:
        """Get the address of the current account.

        Returns:
            str: The address of the wallet account.
        """
        return self.account.address

    def get_account_key(self) -> str:
        """Get the private key of the current account.

        Returns:
            str: The private key of the wallet account.
        """
        return self.account.key
