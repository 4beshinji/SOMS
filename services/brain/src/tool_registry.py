"""
Tool Registry: OpenAI-compatible function definitions for LLM tool calling.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "ダッシュボードに人間向けタスクを作成する。オフィスの問題を検知した場合に使用。報酬（bounty）はタスクの難易度に応じて設定する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "タスクのタイトル（日本語、簡潔に）"
                    },
                    "description": {
                        "type": "string",
                        "description": "タスクの詳細説明（状況と対応方法を含む）"
                    },
                    "bounty": {
                        "type": "integer",
                        "description": "報酬ポイント。簡単:500-1000、中程度:1000-2000、重労働:2000-5000"
                    },
                    "urgency": {
                        "type": "integer",
                        "description": "緊急度 0-4。0:後回し可、1:低、2:通常、3:高、4:緊急"
                    },
                    "zone": {
                        "type": "string",
                        "description": "タスクの対象ゾーン（例: main, kitchen）"
                    },
                    "task_types": {
                        "type": "string",
                        "description": "タスク種別をカンマ区切りで（例: environment,urgent）"
                    }
                },
                "required": ["title", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_device_command",
            "description": "MCPBridge経由でエッジデバイスにコマンドを送信する。エアコン操作、照明制御、窓の開閉などに使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "デバイスエージェントのID（例: edge_01）"
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "実行するツール名（例: set_temperature, toggle_light）"
                    },
                    "arguments": {
                        "type": "string",
                        "description": "ツール引数をJSON文字列で指定（例: {\"temperature\": 24}）"
                    }
                },
                "required": ["agent_id", "tool_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_zone_status",
            "description": "WorldModelから指定ゾーンの詳細な状態を取得する。判断に追加情報が必要な場合に使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "ゾーンID（例: main, kitchen, meeting_room_a）"
                    }
                },
                "required": ["zone_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "音声でオフィスの人に直接話しかける。タスク発行が不要な場面（健康アドバイス、軽い注意、観察報告など）で使用。ダッシュボードには表示されない。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "読み上げるメッセージ。自然な話し言葉で、70文字以内。"
                    },
                    "zone": {
                        "type": "string",
                        "description": "対象ゾーン"
                    },
                    "tone": {
                        "type": "string",
                        "description": "トーン: neutral(通常), caring(優しく), humorous(ユーモア), alert(注意喚起)"
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_tasks",
            "description": "現在アクティブなタスク一覧を取得する。重複タスク作成を防止するために、タスク作成前に確認すること。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_status",
            "description": "デバイスネットワークの状態を取得する。オフライン、低バッテリー、通信エラーなどの問題を確認できる。デバイスコマンド送信前に状態確認として使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_id": {
                        "type": "string",
                        "description": "ゾーンID（省略時: 全ゾーン）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "在庫状況を確認する。棚センサの重量データに基づく現在の在庫一覧を返す。",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone": {
                        "type": "string",
                        "description": "ゾーンID（省略時: 全ゾーン）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calibrate_shelf",
            "description": "棚センサのキャリブレーションを実行する。2ステップ: step='tare'（空の棚でゼロ点設定）→ step='set_known_weight'（既知重量を載せてスケール設定）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "棚センサのデバイスID（例: shelf_01）"
                    },
                    "step": {
                        "type": "string",
                        "description": "キャリブレーションステップ: 'tare'（ゼロ点設定）または 'set_known_weight'（既知重量設定）"
                    },
                    "known_weight_g": {
                        "type": "number",
                        "description": "既知重量（グラム）。step='set_known_weight' の場合に必須"
                    }
                },
                "required": ["device_id", "step"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_shopping_item",
            "description": "買い物リストに商品を追加する。在庫不足検知時に使用。重複チェックは自動で行われる。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "商品名（例: コーヒー豆）"
                    },
                    "category": {
                        "type": "string",
                        "description": "カテゴリ（例: 飲料、事務用品）"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "購入数量"
                    },
                    "store": {
                        "type": "string",
                        "description": "購入店舗（任意）"
                    },
                    "price": {
                        "type": "number",
                        "description": "参考価格（任意）"
                    },
                    "notes": {
                        "type": "string",
                        "description": "備考（任意）"
                    }
                },
                "required": ["name", "quantity"]
            }
        }
    }
]


def get_tools():
    """Return all tool definitions for LLM."""
    return TOOLS


def get_tool_names():
    """Return list of all tool names."""
    return [t["function"]["name"] for t in TOOLS]
