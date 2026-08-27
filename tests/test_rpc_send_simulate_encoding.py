"""send/simulate requests must advertise base64 when the config is omitted.

The transaction payload is always base64. JSON-RPC defaults to base58 if the
config object is missing or has encoding=null, which real nodes reject.
"""

from __future__ import annotations

import json
import pickle
from typing import Any

from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.rpc.config import RpcSendTransactionConfig, RpcSimulateTransactionConfig
from solders.rpc.requests import (
    GetClusterNodes,
    SendLegacyTransaction,
    SendRawTransaction,
    SendVersionedTransaction,
    SimulateLegacyTransaction,
    SimulateVersionedTransaction,
    batch_to_json,
)
from solders.transaction import Transaction, VersionedTransaction
from solders.transaction_status import UiTransactionEncoding

SEED = bytes([1] * 32)
BLOCKHASH = Hash.default()
PROGRAM_ID = Pubkey.default()


def _legacy_tx() -> Transaction:
    payer = Keypair.from_seed(SEED)
    ix = Instruction(PROGRAM_ID, b"abc", [])
    message = Message([ix], payer.pubkey())
    return Transaction([payer], message, BLOCKHASH)


def _versioned_tx() -> VersionedTransaction:
    payer = Keypair.from_seed(SEED)
    ix = Instruction(PROGRAM_ID, b"abc", [])
    message = Message.new_with_blockhash([ix], payer.pubkey(), BLOCKHASH)
    return VersionedTransaction(message, [payer])


def _assert_base64_payload(payload: dict[str, Any]) -> None:
    params = payload["params"]
    assert len(params) >= 2
    tx_b64 = params[0]
    assert isinstance(tx_b64, str)
    assert any(ch in tx_b64 for ch in "+/")
    assert params[1]["encoding"] == "base64"


def test_omitted_config_uses_python_ctor_defaults_with_base64() -> None:
    legacy = _legacy_tx()
    versioned = _versioned_tx()
    raw = bytes(legacy)
    cases = [
        SendLegacyTransaction(legacy),
        SendVersionedTransaction(versioned),
        SendRawTransaction(raw),
        SimulateLegacyTransaction(legacy),
        SimulateVersionedTransaction(versioned),
    ]
    for req in cases:
        assert req.config is not None
        assert req.config.encoding == UiTransactionEncoding.Base64
        payload = json.loads(req.to_json())
        assert payload["method"] in {"sendTransaction", "simulateTransaction"}
        _assert_base64_payload(payload)
        restored = type(req).from_bytes(bytes(req))
        assert restored == req
        assert pickle.loads(pickle.dumps(req)) == req


def test_python_default_now_matches_ctor_encoding() -> None:
    send_default = RpcSendTransactionConfig.default()
    sim_default = RpcSimulateTransactionConfig.default()
    assert send_default.encoding == UiTransactionEncoding.Base64
    assert sim_default.encoding == UiTransactionEncoding.Base64
    assert send_default == RpcSendTransactionConfig()
    assert sim_default == RpcSimulateTransactionConfig()


def test_python_ctor_config_keeps_existing_fields() -> None:
    legacy = _legacy_tx()
    send_cfg = RpcSendTransactionConfig(skip_preflight=True)
    sim_cfg = RpcSimulateTransactionConfig(sig_verify=True)
    send_payload = json.loads(SendRawTransaction(bytes(legacy), send_cfg).to_json())
    assert send_payload["params"][1]["encoding"] == "base64"
    assert send_payload["params"][1]["skipPreflight"] is True
    sim_payload = json.loads(SimulateLegacyTransaction(legacy, sim_cfg).to_json())
    assert sim_payload["params"][1]["encoding"] == "base64"
    assert sim_payload["params"][1]["sigVerify"] is True


def test_batch_to_json_fills_encoding_and_leaves_neighbors_alone() -> None:
    legacy = _legacy_tx()
    versioned = _versioned_tx()
    batch = json.loads(
        batch_to_json(
            [
                GetClusterNodes(0),
                SendLegacyTransaction(legacy),
                SimulateVersionedTransaction(versioned),
            ]
        )
    )
    assert batch[0] == json.loads(GetClusterNodes(0).to_json())
    _assert_base64_payload(batch[1])
    _assert_base64_payload(batch[2])
