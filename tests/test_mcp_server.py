"""第5回: MCP サーバーとクライアントの配線テスト（LLM も API キーも使わない）。

app/mcp_servers.json の glossary サーバーを実際に起動し（stdio）、TestModel で
「ツールが MCP 経由で公開され、呼ばれ、結果が戻るか」を確かめる。
"""

import json

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app.agent import MCP_CONFIG, build_mcp_agent

GLOSSARY_TOOL = "glossary_search_glossary"  # 設定ファイルのサーバー名 "glossary" が前に付く
MAKE_QUIZ_TOOL = "glossary_make_quiz"


def _glossary_only_config(tmp_path):
    """設定のうち glossary サーバーだけを使う（演習で足した fetch などの外部サーバーは起動しない）。"""
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    assert "glossary" in config["mcpServers"], "app/mcp_servers.json に glossary サーバーが必要"
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps({"mcpServers": {"glossary": config["mcpServers"]["glossary"]}}), encoding="utf-8"
    )
    return path


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_glossary_server_exposes_search_tool(tmp_path):
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert GLOSSARY_TOOL in offered  # 演習でツールを足しても壊れないよう「含む」で判定


def test_glossary_result_comes_back_through_mcp(tmp_path):
    model = TestModel(call_tools=[GLOSSARY_TOOL])
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("LoRAとは？", model=model)

    assert [p.tool_name for p in _parts(result, ToolCallPart)] == [GLOSSARY_TOOL]
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == GLOSSARY_TOOL
    assert str(returns[0].content).strip()  # 検索結果（または「見つかりませんでした」）が戻っている
    assert result.output


def test_make_quiz_is_exposed_and_called_through_mcp(tmp_path):
    """第3回の make_quiz を公開した1行（TODO）が効いているかを、ツール一覧と呼び出し結果の両方で確認する。"""
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)
    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert MAKE_QUIZ_TOOL in offered

    # seed=1 だと lecture=1 が生成され、用語集にある回なので成功する
    model = TestModel(call_tools=[MAKE_QUIZ_TOOL], seed=1)
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("第1回の確認問題を出して", model=model)
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == MAKE_QUIZ_TOOL
    quiz = json.loads(returns[0].content)
    assert "question" in quiz and "answer" in quiz


def test_make_quiz_invalid_lecture_becomes_retryable_tool_error_via_mcp(tmp_path):
    """範囲外の回（引数の範囲チェック）を渡すと、tools.make_quiz は ValueError を送出する。

    直接登録した場合はこの例外がそのまま伝播してエージェントの実行が落ちるが、MCP サーバー経由だと
    サーバー側で捕まって「ツールがエラーを返した（is_error）」結果になり、モデルへの retry プロンプトに
    変わる。ただし詳細な理由（第何回の用語集がないか）はサーバー側に留まり、モデルに届くメッセージは
    "Error executing tool make_quiz" という汎用的なものに変わる。
    TestModel は受け取ったメッセージを読んで引数を直すことはしないため、同じ（範囲外の）引数で呼び直し、
    最終的に最大リトライ回数を超えて `UnexpectedModelBehavior` になる。
    """
    # seed=0 だと lecture=0 が生成され、用語集に無い回なので ValueError になる
    model = TestModel(call_tools=[MAKE_QUIZ_TOOL], seed=0)
    with pytest.raises(UnexpectedModelBehavior, match=MAKE_QUIZ_TOOL):
        build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("第0回の確認問題を出して", model=model)
