# 第5回 解答

## 演習

- `--list-tools` で見えたツール名と、第3回（`--mcp` なし）との違い：
  第3回（関数を直接登録）では `search_glossary`・`get_lecture_summary` の2個がそのままの名前で見える。
  第5回（`--mcp`）では同じ2個が `glossary_search_glossary`・`glossary_get_lecture_summary` のように、
  設定ファイル側のサーバー名 `glossary` が接頭辞として付く。複数のサーバーに同名ツールがあっても
  区別できるようにする仕組みだと分かった。
- `--mcp --trace` で見えたツール呼び出し（ツール名と引数）と、`requests` の回数：
  「AIE2026の講座の宿題にある『3レベル』とは何ですか？」に対し、
  `glossary_search_glossary({'query': '3レベル'})` が呼ばれた。`requests` は2回（ツール呼び出し用に1回、
  結果を受けて最終回答を作るために1回）。`--mcp` なしのとき（`search_glossary({'query': '3レベル'})`）と
  比べて、呼び出し回数や回答内容はほぼ同じで、ツール名の接頭辞以外に違いは見られなかった。
- MCP サーバーに公開したツールと、その説明文：
  `app/mcp_server.py` に `server.tool()(tools.get_lecture_summary)` を追加し、`search_glossary` と合わせて
  2つを公開した。説明文は `tools.py` の docstring そのまま：「指定した回（1始まりの整数）の講義の要点を返す。
  『第3回では何を学ぶ？』のように、回の内容や関係を聞かれたときに使う。」
  追加後は `--list-tools` に `glossary_get_lecture_summary` が増え、「第2回では何を学びますか？」という質問で
  実際に `glossary_get_lecture_summary({'lecture': 2})` が呼ばれることを確認した。
- fetch サーバーを足したときのツール呼び出し（ツール名と引数）：
  `app/mcp_servers.json` に `fetch`（`uvx mcp-server-fetch`）を追加し、
  「https://modelcontextprotocol.io/ の冒頭を日本語で3行に要約して」と質問したところ、
  `fetch_fetch({'url': 'https://modelcontextprotocol.io/'})` → 続けて
  `glossary_search_glossary({'query': 'MCP'})` の2回のツール呼び出しが行われた（`requests` は3回）。
  コードは1行も書かず、設定ファイルに5行足すだけで外部ツールが使えるようになった。

## 宿題

- 取り組んだレベル：実装
- やったこと：
  第3回の `make_quiz`（回を指定すると用語集から確認問題を1問作るツール）を `app/tools.py` に実装し、
  `app/agent.py`（直接登録）と `app/mcp_server.py`（MCP サーバー経由）の両方に登録した。
  引数の範囲チェックとして、用語集にその回の項目がない場合は `ValueError`（「第N回の用語集項目が
  見つかりません。用意されている回: [...]」）を送出するようにし、`tests/test_tools.py` に
  正常系・異常系のテストを追加した。そのうえで、`tests/test_mcp_server.py` に
  「MCP 経由でツールが公開・呼び出せるか」と「範囲外の引数を渡したときにどうなるか」のテストを足し、
  `--trace` で実際の挙動（直接登録 vs MCP 経由）を見比べた。
- 結果：
  - 直接登録（`agent.tool_plain`）：`ValueError` がそのまま伝播し、`uv run python -m app.agent --trace
    '第20回の内容から確認問題を1問出して'` はエージェントの実行自体がクラッシュした（スタックトレースが
    そのまま表示される）。
  - MCP 経由（`--mcp --trace`）：同じ質問でもクラッシュせず、`[tool error] glossary_make_quiz -> Error
    executing tool make_quiz…` という表示のあとモデルが別のツール（`glossary_get_lecture_summary`）に
    切り替えて「第20回はまだ用意されていない」という回答を作った。MCP サーバー側（`mcp` パッケージ）が
    例外を捕まえて `isError=True` の結果に変換し、pydantic-ai 側がそれを「ツールへの retry プロンプト」
    （`RetryPromptPart`）として扱うため、モデルに仕切り直す機会が生まれる。
  - ただし MCP 経由だと、こちらが `ValueError` に書いた詳しい理由（「用意されている回: [1, 2, 3, 5]」）は
    モデルに届かず、`Error executing tool make_quiz` という汎用的な文言に置き換わっていた
    （`mcp.server.mcpserver.tools.base.Tool.run` が、素の例外は「クラッシュ」とみなして詳細を
    サーバー側に留め、意図的な `ToolError` だけ理由をそのまま通す実装になっているため）。
  - `uv run pytest -q` は16件すべて成功（直接登録のクラッシュ・MCP経由の retry・正常系をそれぞれテスト化）。
- 気づき・疑問：
  同じ関数・同じ例外でも、「直接登録」と「MCPサーバー経由」でエージェントから見える振る舞いが全く違う
  （前者はプロセス全体が落ちる、後者はモデルに再試行のチャンスが与えられる）のが一番の発見だった。
  MCP はツール側のバグを「クラッシュ」として握りつぶし詳細を隠す設計になっているようで、エラーメッセージの
  詳細までモデルに届けたい場合は `ValueError` ではなく MCP 側が用意している専用のエラー型（`ToolError`
  など）を使う必要がありそうだと分かった（`tools.py` を特定のフレームワークに依存させたくなかったので
  今回は手を付けていない）。第3回の演習で「ツールの例外は何が起きるか確認しよう」という指示を素朴に
  試しただけでは気づけなかった、MCP特有の安全側に倒す設計を知れたのが良かった。
