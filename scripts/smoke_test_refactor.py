#!/usr/bin/env python3
"""Smoke test to validate PipefyClient refactor maintains backward compatibility.

This script performs basic validation without requiring real API credentials.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.types import CardSearch


def test_imports():
    """Test that all imports resolve correctly."""
    print("✅ Testing imports...")
    try:
        from pipefy_mcp.services.pipefy import PipefyClient
        from pipefy_mcp.services.pipefy.pipe_service import PipeService
        from pipefy_mcp.services.pipefy.card_service import CardService
        from pipefy_mcp.services.pipefy.base_client import BasePipefyClient
        from pipefy_mcp.services.pipefy.queries import pipe_queries, card_queries
        from pipefy_mcp.services.pipefy.utils import formatters
        print("   All imports successful")
        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False


def test_public_api():
    """Test that all public API methods exist and have correct signatures."""
    print("✅ Testing public API...")
    client = PipefyClient.__new__(PipefyClient)
    
    required_methods = [
        "get_pipe",
        "get_start_form_fields",
        "create_card",
        "get_card",
        "get_cards",
        "move_card_to_phase",
        "update_card_field",
        "update_card",
    ]
    
    missing = []
    for method in required_methods:
        if not hasattr(client, method):
            missing.append(method)
    
    if missing:
        print(f"   ❌ Missing methods: {missing}")
        return False
    
    print(f"   All {len(required_methods)} public methods present")
    return True


def test_facade_structure():
    """Test that facade has correct internal structure."""
    print("✅ Testing facade structure...")
    try:
        # Use patch to avoid OAuth dependencies
        from unittest.mock import MagicMock, patch
        from gql import Client
        
        mock_client_instance = MagicMock(spec=Client)
        
        with patch(
            "pipefy_mcp.services.pipefy.base_client.BasePipefyClient._create_client",
            return_value=mock_client_instance,
        ):
            client = PipefyClient()
        
        # Verify services are present
        assert hasattr(client, "_pipe_service"), "Missing _pipe_service"
        assert hasattr(client, "_card_service"), "Missing _card_service"
        assert hasattr(client, "client"), "Missing client attribute"
        
        # Verify services are correct types
        from pipefy_mcp.services.pipefy.pipe_service import PipeService
        from pipefy_mcp.services.pipefy.card_service import CardService
        assert isinstance(client._pipe_service, PipeService), "Wrong pipe service type"
        assert isinstance(client._card_service, CardService), "Wrong card service type"
        
        print("   Facade structure correct")
        return True
    except AssertionError as e:
        print(f"   ❌ Structure issue: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_shared_client_injection():
    """Test that services share the same client instance."""
    print("✅ Testing shared client injection...")
    try:
        from unittest.mock import MagicMock, patch
        from gql import Client
        
        mock_client_instance = MagicMock(spec=Client)
        
        with patch(
            "pipefy_mcp.services.pipefy.base_client.BasePipefyClient._create_client",
            return_value=mock_client_instance,
        ):
            client = PipefyClient()
        
        # Verify shared client
        assert client._pipe_service.client is client._card_service.client, \
            "Services don't share the same client"
        assert client.client is client._pipe_service.client, \
            "Public client attribute doesn't match service client"
        
        print("   Shared client injection verified")
        return True
    except AssertionError as e:
        print(f"   ❌ Injection issue: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_type_hints():
    """Test that type hints are present (basic check)."""
    print("✅ Testing type hints...")
    import inspect
    
    client = PipefyClient.__new__(PipefyClient)
    methods = [
        "get_pipe",
        "get_start_form_fields",
        "create_card",
        "get_card",
        "get_cards",
        "update_card",
    ]
    
    missing_hints = []
    for method_name in methods:
        method = getattr(client, method_name)
        sig = inspect.signature(method)
        if sig.return_annotation == inspect.Signature.empty:
            missing_hints.append(f"{method_name} (return)")
        # Check first param (most critical)
        params = list(sig.parameters.values())
        if params and params[0].annotation == inspect.Parameter.empty:
            missing_hints.append(f"{method_name} (param)")
    
    if missing_hints:
        print(f"   ⚠️  Missing type hints: {missing_hints}")
        return False
    
    print("   Type hints present")
    return True


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("PipefyClient Refactor - Smoke Test")
    print("=" * 60)
    print()
    
    tests = [
        ("Imports", test_imports),
        ("Public API", test_public_api),
        ("Facade Structure", test_facade_structure),
        ("Shared Client Injection", test_shared_client_injection),
        ("Type Hints", test_type_hints),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"   ❌ Test '{name}' crashed: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All smoke tests passed!")
        return 0
    else:
        print("⚠️  Some smoke tests failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

