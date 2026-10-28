import claimdocbench

import openadjuster


def test_package_imports_and_uses_the_benchmark_policy() -> None:
    assert openadjuster.__version__
    assert claimdocbench.load_policy().policy_id == "CDB-GHS-OP"
