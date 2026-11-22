"""エージェントの配線テスト。

TestModel は実際のLLMを呼ばない偽モデルで、登録されたツールを全部呼んでから
ダミーの回答を返す。APIキーも利用枠も使わずに、
「ツールが登録され、呼ばれ、結果がモデルに戻るか」を確かめられる。
"""

import pytest
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app.agent import agent

BASE_TOOLS = {"search_glossary", "get_lecture_summary"}


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_base_tools_are_registered_and_called():
    # call_tools は BASE_TOOLS に絞る。make_quiz は引数（回）に既定値がなく、全ツール呼び出しだと
    # TestModel が生成した値（既定は 0）で用語集に無い回を引いて ValueError になりうるため対象外にする。
    model = TestModel(call_tools=list(BASE_TOOLS))
    with agent.override(model=model):
        result = agent.run_sync("LoRAとは？")

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert BASE_TOOLS <= offered  # 演習でツールを足しても壊れないよう「含む」で判定

    called = {p.tool_name for p in _parts(result, ToolCallPart)}
    assert BASE_TOOLS <= called
    assert len(_parts(result, ToolReturnPart)) == len(_parts(result, ToolCallPart))
    assert result.output


def test_glossary_result_reaches_the_model():
    model = TestModel(call_tools=["search_glossary"])
    with agent.override(model=model):
        result = agent.run_sync("RAGとは？")
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "search_glossary"


def test_make_quiz_invalid_lecture_crashes_when_registered_directly():
    """直接登録（tool_plain）した場合、ツール内の ValueError はそのまま伝播し、実行全体が落ちる。

    第5回で同じ関数を MCP サーバー経由にすると、サーバー側で捕まって「ツールのエラー結果」に変わり、
    モデルへの retry プロンプトになる（tests/test_mcp_server.py 参照）。同じ関数・同じ例外でも、
    どちらのツール呼び出し方かで見え方が違う。
    """
    model = TestModel(call_tools=["make_quiz"], seed=0)  # seed=0 は lecture=0（用語集に無い回）を生成する
    with agent.override(model=model):
        with pytest.raises(ValueError, match="用意されている回"):
            agent.run_sync("第0回の確認問題を出して")
