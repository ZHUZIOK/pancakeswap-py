import asyncio
import math
import time
import typing
from decimal import Decimal
from enum import IntEnum

from eth_typing import ChecksumAddress
from web3 import Account, AsyncHTTPProvider, AsyncWeb3
from web3.contract.async_contract import AsyncContract
from web3.types import TxParams
from .constant import (
    PANCAKESSWAP_CONTRACT_V3_FACTORY,
    PANCAKESSWAP_CONTRACT_V3_FACTORY_ABI,
    PANCAKESSWAP_CONTRACT_V3_POOL_ABI,
    PANCAKESSWAP_CONTRACT_V3_ROUTER,
    PANCAKESSWAP_CONTRACT_V3_ROUTER_ABI,
    ERC20_ABI,
    PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER,
    PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_ABI,
    PANCAKESSWAP_CONTRACT_V3_QUOTER,
    PANCAKESSWAP_CONTRACT_V3_QUOTER_ABI,
    PANCAKESSWAP_CONTRACT_QUOTER_V2,
    PANCAKESSWAP_CONTRACT_QUOTER_V2_ABI,
)

DetermineMinAmountZeroRType = typing.Literal["AMOUNT0", "AMOUNT1"]


class Fee(IntEnum):
    """Fee tiers for PancakeSwap V3 pools.

    Attributes:
        LOW (int): 0.01% fee tier (100).
        NORMAL (int): 0.05% fee tier (500).
        MEDIUM (int): 0.3% fee tier (3000).
        HIGH (int): 1% fee tier (10000).
    """

    LOW = 100
    NORMAL = 500
    MEDIUM = 3000
    HIGH = 10000


class PancakeSwapV3:
    """PancakeSwap V3 SDK for interacting with PancakeSwap V3 decentralized exchange.

    This class provides methods for concentrated liquidity management, multi-hop swapping,
    position management, and other advanced DeFi operations on the Binance Smart Chain
    using PancakeSwap V3 protocol.
    """

    def __init__(self, json_rpc: str, private_key: str, gas_several: float = 1.1) -> None:
        """Initialize the PancakeSwap V3 SDK.

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
        self.MAX_UINT256 = 2**256 - 1
        self.MAX_UINT128 = 2**128 - 1
        self.gas_several = gas_several
        self.ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
        self.MIN_TICK = -887272
        self.MAX_TICK = -self.MIN_TICK
        self._tick_spacing = {100: 1, 500: 10, 3_000: 60, 10_000: 200}
        self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT = self.w3.eth.contract(
            PANCAKESSWAP_CONTRACT_V3_ROUTER,
            abi=PANCAKESSWAP_CONTRACT_V3_ROUTER_ABI,
        )
        self.PANCAKESSWAP_CONTRACT_V3_FACTORY_CONTRACT = self.w3.eth.contract(
            PANCAKESSWAP_CONTRACT_V3_FACTORY,
            abi=PANCAKESSWAP_CONTRACT_V3_FACTORY_ABI,
        )
        self.PANCAKESSWAP_CONTRACT_V3_QUOTER_CONTRACT = self.w3.eth.contract(
            PANCAKESSWAP_CONTRACT_V3_QUOTER,
            abi=PANCAKESSWAP_CONTRACT_V3_QUOTER_ABI,
        )

        self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT = self.w3.eth.contract(
            PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER,
            abi=PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_ABI,
        )

        self.PANCAKESSWAP_CONTRACT_QUOTER_V2_CONTRACT = self.w3.eth.contract(
            PANCAKESSWAP_CONTRACT_QUOTER_V2,
            abi=PANCAKESSWAP_CONTRACT_QUOTER_V2_ABI,
        )

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
        token_contract = self._get_contract(token_address)
        transaction = await token_contract.functions.approve(
            guy_addr,
            self.MAX_UINT256,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def _approve_check(self, token_address: str, check_amount: typing.Union[int, float]) -> None:
        """Check if approval is needed for position manager and approve if insufficient.

        Args:
            token_address (str): The address of the token contract.
            check_amount (typing.Union[int, float]): The amount to check allowance against.

        Returns:
            None
        """
        allowance = await self._token_allowance(
            token_address=token_address,
            from_address=self.account.address,
            recipient=self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.address,
        )
        if allowance and allowance > check_amount:
            return
        else:
            await self._token_approve(
                token_address=token_address,
                guy_address=self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.address,
            )

    async def _approve_check_router(self, token_address: str, check_amount: typing.Union[int, float]) -> None:
        """Check if approval is needed for router contract and approve if insufficient.

        Args:
            token_address (str): The address of the token contract.
            check_amount (typing.Union[int, float]): The amount to check allowance against.

        Returns:
            None
        """
        allowance = await self._token_allowance(
            token_address=token_address,
            from_address=self.account.address,
            recipient=self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.address,
        )
        if allowance and allowance > check_amount:
            return
        else:
            await self._token_approve(
                token_address=token_address,
                guy_address=self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.address,
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

    async def get_pool(
        self,
        tokenA: str,
        tokenB: str,
        fee: Fee,
    ) -> ChecksumAddress:
        """Get the pool address for two tokens with a specific fee tier.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            fee (Fee): The fee tier for the pool.

        Returns:
            ChecksumAddress: The address of the liquidity pool contract.
        """
        pool_address = await self.PANCAKESSWAP_CONTRACT_V3_FACTORY_CONTRACT.functions.getPool(
            self._get_checksum_address(tokenA),
            self._get_checksum_address(tokenB),
            fee,
        ).call()
        return self._get_checksum_address(pool_address)

    async def auto_create_pool(
        self,
        tokenA: str,
        tokenB: str,
        sqrt_price_x96: int,
        fee: Fee,
    ) -> str:
        """Create a new V3 pool for two tokens with initial price.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            sqrt_price_x96 (int): The initial square root price in X96 format.
            fee (Fee): The fee tier for the new pool.

        Returns:
            str: The transaction hash of the pool initialization.

        Raises:
            Exception: If the pool already exists.
        """
        pool_address = await self.get_pool(tokenA=tokenA, tokenB=tokenB, fee=fee)
        if pool_address != self.ZERO_ADDRESS:
            raise Exception("The pool already exists. Just add liquidity directly.")

        transaction = await self.PANCAKESSWAP_CONTRACT_V3_FACTORY_CONTRACT.functions.createPool(
            self._get_checksum_address(tokenA),
            self._get_checksum_address(tokenB),
            fee,
        ).build_transaction(await self._build_base_tx())
        await self._send_transaction(transaction)

        pool_address = await self.get_pool(tokenA, tokenB, fee)
        pool_contract = self.w3.eth.contract(pool_address, abi=PANCAKESSWAP_CONTRACT_V3_POOL_ABI)
        init_transaction = await pool_contract.functions.initialize(sqrt_price_x96).build_transaction(await self._build_base_tx())
        return await self._send_transaction(init_transaction)

    def _sort_tokens(self, tokenA: str, tokenB: str) -> tuple[ChecksumAddress, ChecksumAddress]:
        """Sort two token addresses in ascending order.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.

        Returns:
            tuple[ChecksumAddress, ChecksumAddress]: The sorted token addresses (token0, token1).
        """
        tokenA_addr = self._get_checksum_address(tokenA)
        tokenB_addr = self._get_checksum_address(tokenB)

        if tokenA_addr.lower() < tokenB_addr.lower():
            return tokenA_addr, tokenB_addr
        else:
            return tokenB_addr, tokenA_addr

    def _get_min_tick(self, fee: int) -> int:
        """Get the minimum valid tick for a given fee tier.

        Args:
            fee (int): The fee tier value.

        Returns:
            int: The minimum tick value for the fee tier.
        """
        min_tick_spacing: int = self._tick_spacing[fee]
        return -(self.MIN_TICK // -min_tick_spacing) * min_tick_spacing

    def _get_max_tick(self, fee: int) -> int:
        """Get the maximum valid tick for a given fee tier.

        Args:
            fee (int): The fee tier value.

        Returns:
            int: The maximum tick value for the fee tier.
        """
        max_tick_spacing: int = self._tick_spacing[fee]
        return (self.MAX_TICK // max_tick_spacing) * max_tick_spacing

    def _default_tick_range(self, fee: int) -> tuple[int, int]:
        """Get the default tick range for a given fee tier.

        Args:
            fee (int): The fee tier value.

        Returns:
            tuple[int, int]: The minimum and maximum tick values (min_tick, max_tick).
        """
        min_tick = self._get_min_tick(fee)
        max_tick = self._get_max_tick(fee)
        return min_tick, max_tick

    def _nearest_tick(self, tick: int, fee: int) -> int:
        """Round a tick to the nearest valid tick for a given fee tier.

        Args:
            tick (int): The tick value to round.
            fee (int): The fee tier value.

        Returns:
            int: The nearest valid tick value.

        Raises:
            AssertionError: If the provided tick is out of bounds.
        """
        min_tick, max_tick = self._default_tick_range(fee=fee)
        assert min_tick <= tick <= max_tick, f"Provided tick is out of bounds: {(min_tick, max_tick)}"
        tick_spacing = self._tick_spacing[fee]
        rounded_tick_spacing = round(tick / tick_spacing) * tick_spacing

        match rounded_tick_spacing:
            case _ if rounded_tick_spacing < min_tick:
                return rounded_tick_spacing + tick_spacing
            case _ if rounded_tick_spacing > max_tick:
                return rounded_tick_spacing - tick_spacing
            case _:
                return rounded_tick_spacing

    async def get_pool_slot0(
        self,
        tokenA: str,
        tokenB: str,
        fee: Fee,
    ) -> list[typing.Union[int, bool]]:
        """Get the slot0 data from a V3 pool including current price and tick.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            fee (Fee): The fee tier of the pool.

        Returns:
            list[typing.Union[int, bool]]: The slot0 data containing price, tick, and other info.

        Raises:
            Exception: If the pool address is zero (pool doesn't exist).
        """
        pool_address = await self.get_pool(tokenA, tokenB, fee)
        if pool_address == self.ZERO_ADDRESS:
            raise Exception("pool_address is 0x0000000000000000000000000000000000000000 error.")
        pool_contract = self.w3.eth.contract(pool_address, abi=PANCAKESSWAP_CONTRACT_V3_POOL_ABI)
        slot0: list[typing.Union[int, bool]] = await pool_contract.functions.slot0().call()
        return slot0

    async def get_pool_liquidity(
        self,
        tokenA: str,
        tokenB: str,
        fee: Fee,
    ) -> int:
        """Get the total liquidity in a V3 pool.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            fee (Fee): The fee tier of the pool.

        Returns:
            int: The total liquidity in the pool. Returns 0 if pool doesn't exist.
        """
        pool_address = await self.get_pool(tokenA, tokenB, fee)
        if pool_address == self.ZERO_ADDRESS:
            return 0
        pool_contract = self.w3.eth.contract(
            pool_address,
            abi=PANCAKESSWAP_CONTRACT_V3_POOL_ABI,
        )
        return int(await pool_contract.functions.liquidity().call())

    def _sort_tokens_and_amounts(
        self,
        tokenA: str,
        tokenB: str,
        amountA: typing.Union[int, float],
        amountB: typing.Union[int, float],
    ) -> tuple[str, str, typing.Union[int, float], typing.Union[int, float]]:
        """Sort tokens and their corresponding amounts by token address.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (typing.Union[int, float]): The amount of the first token.
            amountB (typing.Union[int, float]): The amount of the second token.

        Returns:
            tuple[str, str, typing.Union[int, float], typing.Union[int, float]]:
                The sorted tokens and amounts (token0, token1, amount0, amount1).
        """
        tokenA_addr = self._get_checksum_address(tokenA)
        tokenB_addr = self._get_checksum_address(tokenB)

        if tokenA_addr.lower() < tokenB_addr.lower():
            return tokenA_addr, tokenB_addr, amountA, amountB
        else:
            return tokenB_addr, tokenA_addr, amountB, amountA  # 交换代币和数量

    def _price_pct_to_tick_range(self, pct: float) -> int:
        """Calculate tick offset based on percentage price change.

        Args:
            pct (float): The percentage price change (e.g., 0.02 for 2%).

        Returns:
            int: The corresponding tick range offset.
        """
        upper_price = 1 + pct
        tick_range = int(math.log(upper_price) / math.log(1.0001))
        return tick_range

    async def _price_range_pct_tick(
        self,
        tokenA: str,
        tokenB: str,
        fee: Fee,
        price_range_pct: float,
    ) -> tuple[int, int]:
        """Calculate tick range based on percentage around current price.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            fee (Fee): The fee tier of the pool.
            price_range_pct (float): The percentage range around current price.

        Returns:
            tuple[int, int]: The lower and upper tick values (tick_lower, tick_upper).
        """
        pool_address = await self.get_pool(
            tokenA=tokenA,
            tokenB=tokenB,
            fee=fee,
        )
        pool_contract = self.w3.eth.contract(
            pool_address,
            abi=PANCAKESSWAP_CONTRACT_V3_POOL_ABI,
        )
        slot0 = await pool_contract.functions.slot0().call()
        current_tick: int = slot0[1]
        tick_spacing = self._tick_spacing[fee]
        tick_range = self._price_pct_to_tick_range(price_range_pct)
        raw_lower = current_tick - tick_range
        raw_upper = current_tick + tick_range
        tick_lower = (raw_lower // tick_spacing) * tick_spacing
        tick_upper = (raw_upper // tick_spacing) * tick_spacing

        nearest_tick_lower = self._nearest_tick(tick_lower, fee)
        nearest_tick_upper = self._nearest_tick(tick_upper, fee)
        return nearest_tick_lower, nearest_tick_upper

    async def auto_create_liquidity(
        self,
        tokenA: str,
        tokenB: str,
        amountA: typing.Union[int, float],
        amountB: typing.Union[int, float],
        tick_lower: typing.Optional[int] = None,
        tick_upper: typing.Optional[int] = None,
        fee: Fee = Fee.NORMAL,
        slippage: float = 0.05,
        price_range_pct: float = 0.02,
    ):
        """Create a new liquidity position in a V3 pool.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (typing.Union[int, float]): The amount of tokenA to provide.
            amountB (typing.Union[int, float]): The amount of tokenB to provide.
            tick_lower (typing.Optional[int], optional): The lower tick of the position.
                Defaults to None (calculated from price_range_pct).
            tick_upper (typing.Optional[int], optional): The upper tick of the position.
                Defaults to None (calculated from price_range_pct).
            fee (Fee, optional): The fee tier for the pool. Defaults to Fee.NORMAL.
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).
            price_range_pct (float, optional): The price range percentage if ticks not provided.
                Defaults to 0.02 (2%).

        Returns:
            str: The transaction hash of the position creation.

        Raises:
            ValueError: If token amounts are not greater than 0 or slippage is invalid.
        """
        if amountA <= 0 or amountB <= 0:
            raise ValueError("The number of tokens must be greater than 0.")
        if not (0 < slippage < 1):
            raise ValueError("The slider must be between 0 and 1.")

        token0_addr, token1_addr, amount0_input, amount1_input = self._sort_tokens_and_amounts(
            tokenA=tokenA,
            tokenB=tokenB,
            amountA=amountA,
            amountB=amountB,
        )

        tick_lower, tick_upper = await self._price_range_pct_tick(
            tokenA=tokenA,
            tokenB=tokenB,
            fee=fee,
            price_range_pct=price_range_pct,
        )

        token0, token1 = map(self._get_checksum_address, [token0_addr, token1_addr])
        token0_decimal, token1_decimal = await asyncio.gather(
            self._token_decimal(token0),
            self._token_decimal(token1),
        )
        amount0_desired_wei = int(Decimal(f"1e{token0_decimal}") * Decimal(str(amount0_input)))
        amount1_desired_wei = int(Decimal(f"1e{token1_decimal}") * Decimal(str(amount1_input)))

        amount0_min = int(Decimal(amount0_desired_wei) * Decimal(str(1 - slippage)))
        amount1_min = int(Decimal(amount1_desired_wei) * Decimal(str(1 - slippage)))

        await asyncio.gather(
            self._approve_check(token0, amount0_desired_wei),
            self._approve_check(token1, amount1_desired_wei),
        )

        recipient = self.account.address
        deadline = int(time.time()) + 60 * 20

        mint_params = (
            token0,
            token1,
            fee,
            tick_lower,
            tick_upper,
            amount0_desired_wei,
            amount1_desired_wei,
            amount0_min,
            amount1_min,
            recipient,
            deadline,
        )
        transaction = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.mint(mint_params).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_increase_liquidity(
        self,
        token_id: int,
        tokenA: str,
        tokenB: str,
        amountA: typing.Union[int, float],
        amountB: typing.Union[int, float],
        slippage: float = 0.05,
    ) -> str:
        """Add liquidity to an existing V3 position.

        Args:
            token_id (int): The NFT token ID of the position.
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (typing.Union[int, float]): The amount of tokenA to add.
            amountB (typing.Union[int, float]): The amount of tokenB to add.
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).

        Returns:
            str: The transaction hash of the liquidity increase.

        Raises:
            Exception: If tokenA and tokenB don't match the position.
        """
        position_info = await self.get_position_info(token_id)
        if tokenA not in position_info or tokenB not in position_info:
            raise Exception("tokenA and tokenB error.")

        pool_slot0 = await self.get_pool_slot0(
            tokenA=tokenA,
            tokenB=tokenB,
            fee=Fee.NORMAL,
        )
        current_tick: int = pool_slot0[1]
        tick_lower: int = position_info[5]
        tick_upper: int = position_info[6]

        token0_addr, token1_addr, amount0_input, amount1_input = self._sort_tokens_and_amounts(
            tokenA=tokenA,
            tokenB=tokenB,
            amountA=amountA,
            amountB=amountB,
        )

        zero_target = self._determine_min_amount_zero(
            current_tick,
            tick_lower,
            tick_upper,
            amount0_input,
            amount1_input,
        )

        token0, token1 = map(self._get_checksum_address, [token0_addr, token1_addr])
        token0_decimal, token1_decimal = await asyncio.gather(
            self._token_decimal(token0),
            self._token_decimal(token1),
        )

        amount0_desired_wei = int(Decimal(f"1e{token0_decimal}") * Decimal(str(amount0_input)))
        amount1_desired_wei = int(Decimal(f"1e{token1_decimal}") * Decimal(str(amount1_input)))

        if zero_target == "AMOUNT0":
            amount0_min = 0
            amount1_min = int(Decimal(amount1_desired_wei) * Decimal(str(1 - slippage)))
        else:
            amount0_min = int(Decimal(amount0_desired_wei) * Decimal(str(1 - slippage)))
            amount1_min = 0

        await asyncio.gather(
            self._approve_check(token0, amount0_desired_wei),
            self._approve_check(token1, amount1_desired_wei),
        )

        deadline = int(time.time()) + 60 * 20
        add_params = (
            token_id,
            amount0_desired_wei,
            amount1_desired_wei,
            amount0_min,
            amount1_min,
            deadline,
        )
        transaction = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.increaseLiquidity(
            add_params,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_decrease_liquidity(
        self,
        token_id: int,
        liquidity_percentage: typing.Union[int, float],
        slippage: float = 0.05,
    ) -> str:
        """Remove liquidity from an existing V3 position.

        Args:
            token_id (int): The NFT token ID of the position.
            liquidity_percentage (typing.Union[int, float]): The percentage of liquidity
                to remove (0-1).
            slippage (float, optional): The maximum slippage tolerance. Defaults to 0.05 (5%).

        Returns:
            str: The transaction hash of the liquidity decrease.

        Raises:
            ValueError: If liquidity_percentage is greater than 1.
        """
        if liquidity_percentage > 1:
            raise ValueError("liquidity_percentage cannot be greater than 1.")

        position_info = await self.get_position_info(token_id)
        current_liquidity = position_info[7]
        liquidity_to_remove = int(current_liquidity * liquidity_percentage)

        amount0_min, amount1_min = await self._calculate_remove_amounts(
            token_id=token_id,
            liquidity_to_remove=liquidity_to_remove,
            slippage=slippage,
        )

        deadline = int(time.time()) + 60 * 20
        transaction = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.decreaseLiquidity(
            (
                token_id,
                liquidity_to_remove,
                amount0_min,
                amount1_min,
                deadline,
            ),
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def _calculate_remove_amounts(
        self,
        token_id: int,
        liquidity_to_remove: int,
        slippage: float,
    ) -> list[int]:
        """Calculate minimum amounts to receive when removing liquidity.

        Args:
            token_id (int): The NFT token ID of the position.
            liquidity_to_remove (int): The amount of liquidity to remove.
            slippage (float): The slippage tolerance.

        Returns:
            list[int]: The minimum amounts [amount0_min, amount1_min].
        """
        position_info = await self.get_position_info(token_id)
        tick_lower = position_info[5]
        tick_upper = position_info[6]

        tokenA = position_info[2]
        tokenB = position_info[3]
        fee = position_info[4]

        pool_slot0 = await self.get_pool_slot0(
            tokenA=tokenA,
            tokenB=tokenB,
            fee=fee,
        )
        current_tick: int = pool_slot0[1]

        sqrt_price_current = (1.0001**current_tick) ** 0.5
        sqrt_price_lower = (1.0001**tick_lower) ** 0.5
        sqrt_price_upper = (1.0001**tick_upper) ** 0.5

        if current_tick < tick_lower:
            amount0 = liquidity_to_remove * (1 / sqrt_price_lower - 1 / sqrt_price_upper)
            amount1 = 0
        elif current_tick >= tick_upper:
            amount0 = 0
            amount1 = liquidity_to_remove * (sqrt_price_upper - sqrt_price_lower)
        else:
            amount0 = liquidity_to_remove * (1 / sqrt_price_current - 1 / sqrt_price_upper)
            amount1 = liquidity_to_remove * (sqrt_price_current - sqrt_price_lower)

        return [
            max(0, int(Decimal(str(amount0)) * Decimal(str(1 - slippage)))),
            max(0, int(Decimal(str(amount1)) * Decimal(str(1 - slippage)))),
        ]

    async def get_all_tokenID(self) -> list[int]:
        """Get all NFT token IDs owned by the current account.

        Returns:
            list[int]: List of all owned position token IDs.

        Raises:
            Exception: If no positions are owned (balance is 0).
        """
        tokenID_balance = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.balanceOf(self.account.address).call()
        if not tokenID_balance:
            raise Exception("tokenID_balance is 0.")

        tokenID_tasks = [
            self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.tokenOfOwnerByIndex(
                self.account.address,
                i,
            ).call()
            for i in range(int(tokenID_balance))
        ]
        tokenIDs: list[int] = await asyncio.gather(*tokenID_tasks)
        return tokenIDs

    async def get_collect(self, token_id: int) -> list[int]:
        """Get the collectable fees for a position without executing collection.

        Args:
            token_id (int): The NFT token ID of the position.

        Returns:
            list[int]: The collectable amounts [amount0, amount1].
        """
        collect: list[int] = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.collect(
            (
                token_id,
                self.account.address,
                self.MAX_UINT128,
                self.MAX_UINT128,
            ),
        ).call()
        return collect

    async def auto_collect_fees(self, token_id: int) -> str:
        """Collect accumulated fees from a V3 position.

        Args:
            token_id (int): The NFT token ID of the position.

        Returns:
            str: The transaction hash of the fee collection.
        """
        transaction = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.collect(
            (
                token_id,
                self.account.address,
                self.MAX_UINT128,
                self.MAX_UINT128,
            ),
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_burn_position(self, token_id: int) -> str:
        """Burn (destroy) an empty V3 position NFT.

        Args:
            token_id (int): The NFT token ID of the position to burn.

        Returns:
            str: The transaction hash of the burn transaction.
        """
        transaction = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.burn(
            token_id,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def get_position_info(self, token_id: int) -> tuple:
        """Get detailed information about a V3 position.

        Args:
            token_id (int): The NFT token ID of the position.

        Returns:
            tuple: The position information including tokens, fee, ticks, and liquidity.
        """
        position = await self.PANCAKESSWAP_CONTRACT_V3_POSITION_MANAGER_CONTRACT.functions.positions(
            token_id,
        ).call()
        return position

    async def auto_swap(
        self,
        tokenIn: str,
        tokenOut: str,
        amountIn: typing.Union[int, float],
        fee: Fee,
    ) -> str:
        """Execute a single-hop swap on V3 with exact input amount.

        Args:
            tokenIn (str): The address of the input token.
            tokenOut (str): The address of the output token.
            amountIn (typing.Union[int, float]): The amount of input tokens to swap.
            fee (Fee): The fee tier of the pool to use.

        Returns:
            str: The transaction hash of the swap.
        """
        tokenIn = self._get_checksum_address(tokenIn)
        tokenOut = self._get_checksum_address(tokenOut)
        recipient = self.account.address
        deadline = int(time.time()) + 60 * 20

        token_in_decimal = await self._token_decimal(tokenIn)
        amount_in_wei = int(Decimal(f"1e{token_in_decimal}") * Decimal(str(amountIn)))

        quote_out = await self.PANCAKESSWAP_CONTRACT_QUOTER_V2_CONTRACT.functions.quoteExactInputSingle(
            (
                tokenIn,
                tokenOut,
                amount_in_wei,
                fee,
                0,
            )
        ).call()
        amount_out: int = quote_out[0]

        await self._approve_check_router(tokenIn, amount_in_wei)
        swap_params = (
            tokenIn,
            tokenOut,
            fee,
            recipient,
            deadline,
            amount_in_wei,
            amount_out,
            0,
        )

        transaction = await self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.functions.exactInputSingle(
            swap_params,
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    async def auto_swap_multi_hop(
        self,
        token_path: list[str],
        amountIn: typing.Union[int, float],
        fees: list[Fee],
    ) -> str:
        """Execute a multi-hop swap through multiple pools.

        Args:
            token_path (list[str]): The list of token addresses in the swap path.
            amountIn (typing.Union[int, float]): The amount of input tokens to swap.
            fees (list[Fee]): The fee tiers for each hop in the path.

        Returns:
            str: The transaction hash of the multi-hop swap.

        Raises:
            ValueError: If the length of tokens doesn't match the length of fees + 1.
        """
        recipient = self.account.address
        deadline = int(time.time()) + 60 * 20
        path = self._encode_path(tokens=token_path, fees=fees)

        first_token = token_path[0]
        token_in_decimal = await self._token_decimal(first_token)
        amount_in_wei = int(Decimal(f"1e{token_in_decimal}") * Decimal(str(amountIn)))
        expected_amount_out = await self.PANCAKESSWAP_CONTRACT_QUOTER_V2_CONTRACT.functions.quoteExactInput(
            path,
            amount_in_wei,
        ).call()
        amount_out_min = expected_amount_out[0]
        await self._approve_check_router(first_token, amount_in_wei)

        transaction = await self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.functions.exactInput(
            (
                path,
                recipient,
                deadline,
                amount_in_wei,
                amount_out_min,
            ),
        ).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    def _encode_path(self, tokens: list[str], fees: list[Fee]) -> bytes:
        """Encode the swap path for multi-hop swaps.

        Args:
            tokens (list[str]): The list of token addresses in the swap path.
            fees (list[Fee]): The fee tiers for each hop.

        Returns:
            bytes: The encoded path for the swap.

        Raises:
            ValueError: If len(tokens) != len(fees) + 1.
        """
        if len(tokens) != len(fees) + 1:
            raise ValueError("len(tokens) must be len(fees) + 1")

        result = b""
        for i in range(len(fees)):
            result += bytes.fromhex(tokens[i][2:])
            result += fees[i].to_bytes(3, "big")
        result += bytes.fromhex(tokens[-1][2:])
        return result

    async def WETH(self) -> ChecksumAddress:
        """Get the WETH (Wrapped BNB) address from the router contract.

        Returns:
            ChecksumAddress: The address of the WETH contract.
        """
        weth_address = await self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.functions.WETH9().call()
        return self._get_checksum_address(weth_address)

    async def factory(self) -> ChecksumAddress:
        """Get the factory contract address from the router contract.

        Returns:
            ChecksumAddress: The address of the PancakeSwap V3 factory contract.
        """
        factory_address = await self.PANCAKESSWAP_CONTRACT_V3_ROUTER_CONTRACT.functions.factory().call()
        return self._get_checksum_address(factory_address)

    async def wrap_bnb(self, amount_bnb: typing.Union[int, float]) -> str:
        """Wrap BNB to WBNB tokens.

        Args:
            amount_bnb (typing.Union[int, float]): The amount of BNB to wrap in ether units.

        Returns:
            str: The transaction hash of the wrapping transaction.
        """
        wbnb_contract = self.w3.eth.contract(await self.WETH(), abi=ERC20_ABI)
        base_tx = await self._build_base_tx()
        base_tx["value"] = self.w3.to_wei(amount_bnb, "ether")
        transaction = await wbnb_contract.functions.deposit().build_transaction(base_tx)
        return await self._send_transaction(transaction)

    async def unwrap_wbnb(self, amount_wbnb: typing.Union[int, float]) -> str:
        """Unwrap WBNB tokens back to BNB.

        Args:
            amount_wbnb (typing.Union[int, float]): The amount of WBNB to unwrap in ether units.

        Returns:
            str: The transaction hash of the unwrapping transaction.
        """
        amount = self.w3.to_wei(amount_wbnb, "ether")
        wbnb_contract = self.w3.eth.contract(await self.WETH(), abi=ERC20_ABI)
        transaction = await wbnb_contract.functions.withdraw(amount).build_transaction(await self._build_base_tx())
        return await self._send_transaction(transaction)

    def _determine_min_amount_zero(
        self,
        current_tick: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: typing.Union[int, float],
        amount1_desired: typing.Union[int, float],
    ) -> DetermineMinAmountZeroRType:
        """Determine which token amount should be set to minimum based on position and ratios.

        Args:
            current_tick (int): The current tick of the pool.
            tick_lower (int): The lower tick of the position.
            tick_upper (int): The upper tick of the position.
            amount0_desired (typing.Union[int, float]): The desired amount of token0.
            amount1_desired (typing.Union[int, float]): The desired amount of token1.

        Returns:
            DetermineMinAmountZeroRType: Either "AMOUNT0" or "AMOUNT1" indicating which
                amount should be set to minimum.
        """
        tick_range = tick_upper - tick_lower
        tick_position = current_tick - tick_lower
        relative_position = tick_position / tick_range

        price_at_current = 1.0001**current_tick
        price_at_lower = 1.0001**tick_lower
        price_at_upper = 1.0001**tick_upper

        sqrt_price_current = price_at_current**0.5
        sqrt_price_lower = price_at_lower**0.5
        sqrt_price_upper = price_at_upper**0.5

        theoretical_ratio = (sqrt_price_current - sqrt_price_lower) / (1 / sqrt_price_current - 1 / sqrt_price_upper)
        actual_ratio = amount1_desired / amount0_desired if amount0_desired > 0 else float("inf")

        if actual_ratio > theoretical_ratio * 1.05:
            return "AMOUNT1"
        elif actual_ratio < theoretical_ratio * 0.95:
            return "AMOUNT0"
        else:
            return "AMOUNT0" if relative_position < 0.5 else "AMOUNT1"

    def get_account_address(self) -> str:
        """Get the address of the current account.

        Returns:
            str: The address of the wallet account.
        """
        return self.account.address

    def get_account_key(self) -> str:
        """Get the private key of the current account in hex format.

        Returns:
            str: The private key of the wallet account as a hex string.
        """
        return self.account.key.hex()

    async def calculate_sqrt_price_x96(
        self,
        tokenA: str,
        tokenB: str,
        amountA: typing.Union[int, float],
        amountB: typing.Union[int, float],
    ) -> int:
        """Calculate the square root price in X96 format for pool initialization.

        This method calculates the initial price for a V3 pool by determining the square root
        of the price ratio between two tokens, adjusted for their decimal differences, and
        formatted in the X96 fixed-point representation used by Uniswap V3/PancakeSwap V3.

        Args:
            tokenA (str): The address of the first token.
            tokenB (str): The address of the second token.
            amountA (typing.Union[int, float]): The amount of tokenA used for price calculation.
            amountB (typing.Union[int, float]): The amount of tokenB used for price calculation.

        Returns:
            int: The square root price in X96 format (sqrt(price) * 2^96). This value is used
                for pool initialization and represents the price of tokenA in terms of tokenB.
        """
        decimals_token0, decimals_token1 = await asyncio.gather(
            self._token_decimal(tokenA),
            self._token_decimal(tokenB),
        )
        price = Decimal(str(amountA)) / Decimal(str(amountB))
        adjusted_price = price * (10 ** (decimals_token0 - decimals_token1))
        sqrt_price = math.sqrt(adjusted_price)
        return int(sqrt_price * (2**96))
