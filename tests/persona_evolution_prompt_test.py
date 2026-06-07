import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.persona.engine import PersonaEngine
from ai_companion.persona.loader import PersonaLoader


def _write_persona_bundle(persona_dir: Path) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / "profile.json").write_text(
        json.dumps(
            {
                "id": "prompt_bot",
                "name": "测试 Bot",
                "age": 24,
                "occupation": "插画师",
                "personality_tags": ["温柔", "克制"],
                "relationship_to_user": "朋友",
                "interests": ["绘画"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "backstory.json").write_text(
        json.dumps(
            {
                "summary": "她原本是个偏安静的人。",
                "key_moments": ["第一次见面"],
                "shared_experiences": ["稳定区里的共同经历"],
                "life_experiences": ["稳定区里的人生经历"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "values.json").write_text(
        json.dumps({"non_negotiable": ["不要欺骗"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (persona_dir / "speaking_style.json").write_text(
        json.dumps({"tone": "自然"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (persona_dir / "conversation_style_rules.json").write_text(
        json.dumps({}, ensure_ascii=False),
        encoding="utf-8",
    )


class PersonaEvolutionPromptTest(unittest.TestCase):
    def test_system_prompt_separates_stable_and_forming_self(self):
        with TemporaryDirectory(prefix="persona-evolution-prompt-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            (persona_dir / "runtime_profile.json").write_text(
                json.dumps(
                    {
                        "relationship_to_user": "暧昧中",
                        "shared_experiences": ["最近一起熬夜准备了一次重要面试"],
                        "life_experiences": ["最近开始重新安排自己的日程"],
                        "shared_growth_summary": "这些共同经历让她最近越来越习惯先接住用户的情绪。",
                        "life_growth_summary": "这些人生经历让她最近更主动地规划自己的生活。",
                        "relationship_state": {
                            "narrative": "你们最近明显比之前更靠近。",
                            "current_posture": "可以更自然地流露熟悉感。",
                            "interaction_guidance": "先承接情绪，再自然带出共同经历。",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (persona_dir / "evolution_state.json").write_text(
                json.dumps(
                    {
                        "runtime_reflection": {
                            "shared_growth_summary": "最近共同经历让她更愿意暴露自己的柔软。",
                            "life_growth_summary": "最近的人生推进让她更敢于定义自己。",
                            "active_personality_drift": ["最近逐渐显得更主动、更愿意表达在意"],
                            "active_style_drift": ["最近越来越习惯先接情绪，再给建议"],
                            "active_value_drift": ["最近更重视关系里的稳定回应"],
                            "latest_relationship_drift": "这段关系最近正在从熟悉走向更亲近。",
                        },
                        "pending_promotions": [
                            {
                                "id": "pending-style",
                                "field_path": "speaking_style.style_notes",
                                "summary": "先接情绪再给建议的表达方式已经很稳定",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            persona = PersonaLoader(persona_dir).load()
            prompt = PersonaEngine(persona).build_system_prompt()

        self.assertIn("【稳定人格与原始背景】", prompt)
        self.assertIn("【最近共同经历与个人人生经历】", prompt)
        self.assertIn("【最近正在形成的变化】", prompt)
        self.assertIn("【当前关系姿态与互动指导】", prompt)
        self.assertIn("稳定区里的共同经历", prompt)
        self.assertIn("最近一起熬夜准备了一次重要面试", prompt)
        self.assertIn("最近逐渐显得更主动、更愿意表达在意", prompt)
        self.assertIn("speaking_style.style_notes", prompt)
        self.assertIn("你们最近明显比之前更靠近。", prompt)


if __name__ == "__main__":
    unittest.main()
