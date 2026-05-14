contract BAFCToken {
address owner = msg.sender;
mapping (address => bool) public frozenAccount; /****** modifiers ******/
modifier onlyOwner {
if (owner == msg.sender) {
_; } else {
InvalidCaller(msg.sender); throw;}
}
modifier unFrozenAccount{
require(!frozenAccount[msg.sender]);
_; }
 /****** Functions *******/
function UBSexToken () public { owner = msg.sender; totalSupply = 1.9 * 10 ** 26;
}
function freezeAccount(address target, bool freeze)
onlyOwner public { frozenAccount[target]=freeze;
}
function switchLiquidity(bool _transferable) onlyOwner{
      transferable=_transferable;
  }
function transfer(address _to, uint _value) unFrozenAccount onlyTransferable {
                             if (frozenAccount[_to]) {
InvalidAccount(_to, "Frozen receiver account");}
else { balances[msg.sender]=balances[msg.sender].sub(
       _value);
  balances[_to] = balances[_to].add(_value);
}
}
}