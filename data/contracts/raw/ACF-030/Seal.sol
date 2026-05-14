function breed() external {
    require(now /1 days > today);
    today += 1;
    uint256 sealPairAmount = sealbalance0f(address(cSeal));
    uint256 tokenPairAmount = token.balanceof(address(cSeal));
    uint256 newSeal = sealPairAmount.mul(spawnRate).div(1e18);
    uint256 amount = UniswapV2Library,getAmountOut(newSeal, seaPairAmount, tokenPairAmount);
    seal.mint(address(cSeal), newSeal);
    if(address(seal) < address(token))
        cSeal.swap(0, amount, address(this),"");
    else
    cSeal.swap(amount, 0, address(this), "");
    token.transfer(address(cSeal), amount);seal.mint(address(cSeal), newSeal);
    cSeal.mint(address(this));
}