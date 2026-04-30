"""Unit tests for agent.adapters.foundry.classify_verdict.

Covers the four-verdict classifier (pass / fail_revert_ac /
fail_error_compile / fail_error_runtime — Day-1 T2 verdict split) across the
revert string variants the plan's Architect flagged as load-bearing:
- OpenZeppelin v4 string reverts ("Ownable: caller is not the owner")
- OpenZeppelin v5 custom errors (OwnableUnauthorizedAccount)
- Custom project-specific errors (NotAuthorized())
- Non-English / non-standard reverts
- Compile failures (→ fail_error_compile) vs OOG/Panic/runtime
  (→ fail_error_runtime). The split lets the cascade router route compile
  failures to "retry the PoC" and runtime non-AC errors to "abstain".
"""

from agent.adapters.foundry import classify_verdict


class TestPassVerdict:
    def test_return_code_0_with_stdout_pass(self):
        r = classify_verdict("[PASS] test_Exploit()", "", 0)
        assert r.verdict == "pass"

    def test_return_code_0_without_explicit_pass_line(self):
        r = classify_verdict("Ran 1 test for test/X.t.sol:XTest\n", "", 0)
        assert r.verdict == "pass"


class TestOzV4StringReverts:
    def test_ownable_caller_not_owner(self):
        r = classify_verdict(
            "[FAIL] test_Exploit()", "Ownable: caller is not the owner", 1
        )
        assert r.verdict == "fail_revert_ac"

    def test_accesscontrol_prefix(self):
        r = classify_verdict(
            "[FAIL]", "AccessControl: account 0xdead is missing role 0x...", 1
        )
        assert r.verdict == "fail_revert_ac"

    def test_bare_unauthorized_word(self):
        r = classify_verdict("[FAIL]", "revert: unauthorized caller", 1)
        assert r.verdict == "fail_revert_ac"


class TestOzV5CustomErrors:
    def test_ownable_unauthorized_account(self):
        r = classify_verdict(
            "[FAIL] test_Exploit()",
            "OwnableUnauthorizedAccount(0x0123456789abcdef)",
            1,
        )
        assert r.verdict == "fail_revert_ac"

    def test_accesscontrol_unauthorized_account(self):
        r = classify_verdict(
            "[FAIL]",
            "AccessControlUnauthorizedAccount(0xdead, 0xrole...)",
            1,
        )
        assert r.verdict == "fail_revert_ac"


class TestProjectCustomErrors:
    def test_notauthorized_error(self):
        r = classify_verdict("[FAIL]", "custom error NotAuthorized()", 1)
        assert r.verdict == "fail_revert_ac"

    def test_notowner_error(self):
        r = classify_verdict("[FAIL]", "NotOwner(address)", 1)
        assert r.verdict == "fail_revert_ac"


class TestNonAccessControlReverts:
    def test_out_of_gas_is_fail_error_runtime(self):
        r = classify_verdict("[FAIL]", "EvmError: OutOfGas", 1)
        assert r.verdict == "fail_error_runtime"

    def test_panic_is_fail_error_runtime(self):
        r = classify_verdict("[FAIL]", "Panic(0x01): Assertion failed", 1)
        assert r.verdict == "fail_error_runtime"

    def test_overflow_is_fail_error_runtime(self):
        r = classify_verdict("[FAIL]", "Panic(0x11): Arithmetic overflow", 1)
        assert r.verdict == "fail_error_runtime"


class TestCompileFailures:
    def test_parser_error(self):
        r = classify_verdict(
            "",
            "ParserError: Expected ';' but got '}'",
            1,
        )
        assert r.verdict == "fail_error_compile"

    def test_identifier_not_found(self):
        r = classify_verdict(
            "",
            "Error (7576): Undeclared identifier. IdentifierNotFound",
            1,
        )
        assert r.verdict == "fail_error_compile"

    def test_type_error(self):
        r = classify_verdict(
            "",
            "TypeError: Operator not compatible with types",
            1,
        )
        assert r.verdict == "fail_error_compile"

    def test_declaration_error(self):
        r = classify_verdict("", "DeclarationError: duplicate", 1)
        assert r.verdict == "fail_error_compile"

    def test_unresolved_import(self):
        r = classify_verdict(
            "",
            "Error: unresolved import '@openzeppelin/contracts/...'",
            1,
        )
        assert r.verdict == "fail_error_compile"


class TestVerdictSplitDistinction:
    """Day-1 T2 — confirm compile-fail and runtime-fail are now distinguishable.

    These two verdicts route differently in the Day-2 cascade: compile failures
    retry the PoC; runtime non-AC reverts post-retry route to abstain.
    """

    def test_compile_and_runtime_are_distinct(self):
        compile_r = classify_verdict("", "ParserError: bad token", 1)
        runtime_r = classify_verdict("[FAIL]", "EvmError: OutOfGas", 1)
        assert compile_r.verdict == "fail_error_compile"
        assert runtime_r.verdict == "fail_error_runtime"
        assert compile_r.verdict != runtime_r.verdict


class TestEdgeCases:
    def test_both_ac_and_non_ac_keywords_not_ac(self):
        """If OutOfGas co-occurs with an AC keyword, treat as runtime fail
        (non-AC wins to avoid misclassifying infra errors as safe)."""
        r = classify_verdict(
            "[FAIL]", "OutOfGas during Ownable: caller is not the owner", 1
        )
        assert r.verdict == "fail_error_runtime"

    def test_empty_output(self):
        r = classify_verdict("", "", 1)
        assert r.verdict == "fail_error_runtime"

    def test_error_summary_bounded(self):
        r = classify_verdict("", "error " * 1000, 1)
        assert len(r.error_summary) <= 500


class TestSelfContainedPocDetection:
    """Verify the `poc_imports_original` path logic in run_forge_test (doc-test
    equivalent — we can't run forge in unit tests so we check the substring
    detection directly).
    """

    @staticmethod
    def _imports_original(poc_code: str, contract_name: str) -> bool:
        return (
            f"../src/{contract_name}" in poc_code
            or f'"src/{contract_name}' in poc_code
        )

    def test_standalone_poc_detected_as_not_importing(self):
        poc = """
        pragma solidity 0.8.20;
        import "forge-std/Test.sol";
        contract X { function f() external {} }
        contract XTest is Test { function test_x() public { X(address(0)).f(); } }
        """
        assert self._imports_original(poc, "X") is False

    def test_importing_from_src_detected(self):
        poc = 'import "../src/MyContract.sol";'
        assert self._imports_original(poc, "MyContract") is True

    def test_double_quote_src_prefix_detected(self):
        poc = 'import "src/MyContract.sol";'
        assert self._imports_original(poc, "MyContract") is True

    def test_different_contract_name_not_detected(self):
        poc = 'import "../src/OtherContract.sol";'
        assert self._imports_original(poc, "MyContract") is False
