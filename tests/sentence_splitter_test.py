import unittest

from ai_companion.bot.response_style import ResponseStylePolisher
from ai_companion.gateway.sentence_splitter import SentenceSplitter


class SentenceSplitterTest(unittest.TestCase):
    def test_preserves_combo_punctuation_as_single_boundary(self):
        text = "真的？！你现在才说。啊！？不是吧！！"
        self.assertEqual(
            SentenceSplitter.split(text),
            ["真的？！", "你现在才说。", "啊！？", "不是吧！！"],
        )

    def test_preserves_ellipsis_followed_by_question_mark(self):
        text = "等等……？你认真的？"
        self.assertEqual(SentenceSplitter.split(text), ["等等……？", "你认真的？"])

    def test_keeps_trailing_quotes_and_parentheses_with_sentence(self):
        text = '她看着我说：“真的？！”我愣住了。He said, "Really?" Then left.'
        self.assertEqual(
            SentenceSplitter.split(text),
            ['她看着我说：“真的？！”', "我愣住了。", 'He said, "Really?"', "Then left."],
        )

    def test_keeps_nested_closers_after_sentence_end(self):
        text = '他低声补了一句（“好。”）然后走了。'
        self.assertEqual(
            SentenceSplitter.split(text),
            ['他低声补了一句（“好。”）', "然后走了。"],
        )

    def test_splits_on_ascii_question_and_exclamation_marks(self):
        text = "Really!? You say that now! Fine?"
        self.assertEqual(
            SentenceSplitter.split(text),
            ["Really!?", "You say that now!", "Fine?"],
        )

    def test_splits_on_newlines_without_empty_fragments(self):
        text = "第一句\n\n第二句？！\r\n第三句"
        self.assertEqual(SentenceSplitter.split(text), ["第一句", "第二句？！", "第三句"])


class ResponseStylePolisherSentenceTest(unittest.TestCase):
    def test_first_sentences_reuses_sentence_splitter_rules(self):
        polisher = ResponseStylePolisher()
        text = "真的？！你现在才说。啊！？不是吧！！"
        self.assertEqual(polisher._first_sentences(text, 2), "真的？！你现在才说。")
