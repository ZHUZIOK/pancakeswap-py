<p align="center">
  <img src="https://github.com/ZHUZIOK/pancakeswap-py/blob/main/docs/images/pancankeswap_py_logo.png?raw=true" alt="pancankeswap_py_logo" width="120"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/your-package-name.svg)](https://pypi.org/project/pancakeswap-py/)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)
![License](https://img.shields.io/badge/license-MIT-yellow)

## pancakeswap-py  🍪🐍
A Python library based on web3.py, Asyncio, and PancakeSwap V2/V3 contracts, featuring pool creation, liquidity management, liquidity removal, liquidity viewing, swap trading, WBNB/BNB conversion, and more. V2/V3 use consistent syntax as much as possible, making it convenient for beginners to perform DeFi operations on the BSC network.

<a href="https://github.com/ZHUZIOK/pancakeswap-py/blob/main/docs/zh-CN_README.md">中文文档</a>


## ⚡ Quick Start

### Installation
```Python
pip install pancakeswap-py
```
```Python
uv add pancakeswap-py
```
## V3 Examples

### Prerequisites
> 💡 It's recommended to use private or privacy-focused RPC nodes to prevent sandwich attacks

```Python
from pancakeswap_py.v3 import PancakeSwapV3, Fee
pancakeswap_v3 = PancakeSwapV3(
    json_rpc=JSON_RPC,
    private_key=PRIVATE_KEY,
)
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
# 💡 Test token with no value
TOKEN = "0x7e216C64f5954758d747e61C3b58062509eE40B8"
amountA = 0.001
amountB = 100
```
> 💡 All methods with the `auto` prefix are wrapped by the author for ease of use by beginners  
> 💡 All slippage defaults to `0.05`  
> 💡 Both V2/V3 classes include `WBNB/BNB` conversion methods: `wrap_bnb/unwrap_wbnb`

### Create Pool
```Python
sqrt_price_x96 = await pancakeswap_v3.calculate_sqrt_price_x96(
    tokenA=WBNB,
    tokenB=TOKEN,
    amountA=amountA,
    amountB=amountB,
)
tx_hash = await pancakeswap_v3.auto_create_pool(
    tokenA=WBNB,
    tokenB=TOKEN,
    sqrt_price_x96=sqrt_price_x96,
    fee=Fee.NORMAL,
)
#sqrt_price_x96:250541448375047936131727360
#tx_hash:24bed0415fd2d83f53f682f1d8a5780c973662827f29af9115146a3afc832bfe
```
#### Create Liquidity
```Python
tx_hash = await pancakeswap_v3.auto_create_liquidity(
    tokenA=WBNB,
    tokenB=TOKEN,
    amountA=amountA,
    amountB=amountB,
)
#tx_hash:b8ccee2cfc258979f93d6fcae672692b2ceaad9b7e35d981a26e7cc9ec2feed1
```
#### Get All Token IDs for Address
```Python
all_tokenID = await pancakeswap_v3.get_all_tokenID()
#all_tokenID:[2823169]
```
#### Add Liquidity
```Python
tx_hash = await pancakeswap_v3.auto_increase_liquidity(
    tokenA=WBNB,
    tokenB=TOKEN,
    amountA=amountA,
    amountB=amountB,
    token_id=token_id,
)
#tx_hash:36ff8bda68c9e959e49f3ef798cea4c6996c12bd0197de6bf26f54b16a14fe7f
```
#### Swap Trading
```Python
tx_hash = await pancakeswap_v3.auto_swap(
        tokenIn=WBNB,
        tokenOut=TOKEN,
        amountIn=0.0001,
        fee=Fee.NORMAL,
    )
#tx_hash:2abc0a2e19d8792b852c11aebdce185dba0348b8018f397c9acf937c64cca70e
```
#### View Liquidity
```Python
pool_liquidity = await pancakeswap_v3.get_pool_liquidity(
    tokenA=WBNB,
    tokenB=TOKEN,
    fee=Fee.NORMAL,
)
#pool_liquidity:62026147965412118004
```
#### View Position
```Python
position_info = await pancakeswap_v3.get_position_info(
    token_id = token_id,
)
#position_info:[0, '0x0000000000000000000000000000000000000000', '0x7e216C64f5954758d747e61C3b58062509eE40B8', '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c', 500, -115340, -114940, 62026147965412118004, 0, 0, 0, 0]
```
#### Remove Liquidity
```Python
tx_hash = await pancakeswap_v3.auto_decrease_liquidity(
    token_id=token_id,
    liquidity_percentage=1,  # 1 means remove all
)
#tx_hash:5c59426baf1662824c33208d13ca9459da445458e02414e33657a4ab95c48f4f
```
#### Collect Fees
```Python
tx_hash = await pancakeswap_v3.auto_collect_fees(
    token_id = 2823169,
)
#tx_hash:c396af7ec749edf88a02cfb2af230978053061e28642f0728b08066971011448
```
#### Burn Position
```Python
tx_hash = await pancakeswap_v3.auto_burn_position(
    token_id=2823169,
)
#tx_hash:f1746719e0ee85d0bcab108bef8353b1df12060840df022a7815d904d48fcef8
```
#### On-Chain Screenshot
<div style="text-align: center;">
    <img src="https://github.com/ZHUZIOK/pancakeswap-py/blob/main/docs/images/screenshot_on_the_chain_v3.png?raw=true" alt="pancankeswap_py_logo" title="pancankeswap_py_logo" style="max-width: 100%; height: auto;">
</div>

## V2 Examples
### Prerequisites
```Python
from pancakeswap_py.v2 import PancakeSwapV2

JSON_RPC = os.getenv("JSON_RPC")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

pancakeswap_v2 = PancakeSwapV2(
    json_rpc=JSON_RPC,
    private_key=PRIVATE_KEY,
)

WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
# 💡 Test token with no value!
TOKEN = "0xDD6A7a67466e4c207188Ad3A1E7D0E667C9F00B1"
amountA = 0.001
amountB = 100
```
#### Create Pool
```Python
tx_hash = await pancakeswap_v2.auto_create_pair(
    tokenA=WBNB,
    tokenB=TOKEN,
)
#tx_hash:dfc36bab549723f9cb90203d52b0450c7c830765328af1f062c067ebe67ae2d5
```

#### Create Liquidity
```Python
tx_hash = await pancakeswap_v2.auto_create_liquidity(
    tokenA=WBNB,
    tokenB=TOKEN,
    amountA=amountA,
    amountB=amountB,
)
#tx_hash:0b256eef837c8801fc7243a2158a7100239fddb7290ea305642a6ed2469c4138
```
#### Add Liquidity
```Python
tx_hash = await pancakeswap_v2.auto_increase_liquidity(
    tokenA=WBNB,
    tokenB=TOKEN,
    amountA=amountA,
    amountB=amountB,
)
#tx_hash:cab6bb030664588bfb1ad51e688c4c05a12fa72ba09464475ece94f7e3996d9b
```
#### Get Pool Address
```Python
pair_address = await pancakeswap_v2.get_pair(
    tokenA=WBNB,
    tokenB=TOKEN,
)
#pair_address:0x002693E9eb3B6787034a8C09acB7cb90AFba1C5F
```
#### Get Token Reserves
```Python
reserves = await pancakeswap_v2.get_reserves(
    tokenA=WBNB,
    tokenB=TOKEN,
)
#reserves:(2000000000000000, 200000000000000000000, 1751778446)
```
#### Swap Trading
```Python
tx_hash = await pancakeswap_v2.auto_swap(
    tokenIn=TOKEN,
    tokenOut=WBNB,
    amountIn=10,
)
#tx_hash:a3a0f07b5535d32d876eb2d5716be0aa9835f49e78a9added254246f3d2c48ec
```
#### Remove Liquidity
```Python
tx_hash = await pancakeswap_v2.auto_decrease_liquidity(
    tokenA=TOKEN,
    tokenB=WBNB,
    liquidity_percentage=1,  # 1 means remove all
)
#tx_hash:d38f04a4d87d7ffe2d3b2f24be9011bc1c2394083e5c65a6ce042273537ccfcd
```
#### On-Chain Screenshot
<div style="text-align: center;">
    <img src="https://github.com/ZHUZIOK/pancakeswap-py/blob/main/docs/images/screenshot_on_the_chain_v2.png?raw=true" alt="pancankeswap_py_logo" title="pancankeswap_py_logo" style="max-width: 100%; height: auto;">
</div>