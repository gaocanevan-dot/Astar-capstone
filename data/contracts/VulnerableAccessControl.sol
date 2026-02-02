// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title VulnerableAccessControl
 * @notice 这是一个故意设计的存在访问控制漏洞的合约，用于测试审计系统
 */
contract VulnerableAccessControl {
    address public owner;
    address public admin;
    uint256 public protocolFee;
    bool public paused;

    mapping(address => uint256) public balances;

    event OwnerChanged(address indexed oldOwner, address indexed newOwner);
    event FeeUpdated(uint256 oldFee, uint256 newFee);
    event Withdrawal(address indexed to, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract is paused");
        _;
    }

    constructor() {
        owner = msg.sender;
        admin = msg.sender;
        protocolFee = 100; // 1%
    }

    // ✅ 正确: 有 onlyOwner 保护
    function setOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        emit OwnerChanged(owner, newOwner);
        owner = newOwner;
    }

    // ❌ 漏洞: setProtocolFee 缺少访问控制！
    // 任何人都可以调用此函数修改协议费率
    function setProtocolFee(uint256 _fee) external {
        require(_fee <= 10000, "Fee too high");
        emit FeeUpdated(protocolFee, _fee);
        protocolFee = _fee;
    }

    // ❌ 漏洞: withdraw 缺少访问控制！
    // 任何人都可以提取合约中的资金
    function withdraw(uint256 amount) external whenNotPaused {
        require(address(this).balance >= amount, "Insufficient balance");
        emit Withdrawal(msg.sender, amount);
        payable(msg.sender).transfer(amount);
    }

    // ✅ 正确: 有 onlyOwner 保护
    function pause() external onlyOwner {
        paused = true;
    }

    // ✅ 正确: 有 onlyOwner 保护
    function unpause() external onlyOwner {
        paused = false;
    }

    // 接收 ETH
    receive() external payable {
        balances[msg.sender] += msg.value;
    }
}
