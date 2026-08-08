import unittest
from types import SimpleNamespace

from integrations.omlx import (
    OmlxChatCompletions,
    OmlxOcrCallState,
    has_ocr_output_anomaly,
    has_repetitive_loop,
    trim_repetitive_loop,
)


class FakeCompletions:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.kwargs = None

    def create(self, *args, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                    finish_reason=self.finish_reason,
                )
            ]
        )


class OmlxChatCompletionsTest(unittest.TestCase):
    def create_wrapper(self, completions, state):
        return OmlxChatCompletions(
            completions,
            omlx_base_url="http://127.0.0.1:8000/v1",
            ocr_call_state=state,
            max_tokens=4096,
            temperature=0,
            repetition_penalty=1.1,
        )

    def test_applies_stable_ocr_generation_parameters(self) -> None:
        completions = FakeCompletions("OCR result")
        state = OmlxOcrCallState()

        response = self.create_wrapper(completions, state).create(
            model="ocr-model",
            messages=[],
        )

        self.assertEqual(completions.kwargs["max_tokens"], 4096)
        self.assertEqual(completions.kwargs["temperature"], 0)
        self.assertEqual(
            completions.kwargs["extra_body"]["repetition_penalty"],
            1.1,
        )
        self.assertEqual(response.choices[0].message.content, "OCR result")
        self.assertEqual(state.request_count, 1)
        self.assertEqual(state.errors, [])

    def test_preserves_explicit_generation_parameters(self) -> None:
        completions = FakeCompletions("OCR result")
        state = OmlxOcrCallState()

        self.create_wrapper(completions, state).create(
            model="ocr-model",
            messages=[],
            max_tokens=100,
            temperature=0.2,
            extra_body={"repetition_penalty": 1.2},
        )

        self.assertEqual(completions.kwargs["max_tokens"], 100)
        self.assertEqual(completions.kwargs["temperature"], 0.2)
        self.assertEqual(
            completions.kwargs["extra_body"]["repetition_penalty"],
            1.2,
        )

    def test_caps_image_generation_without_changing_text_generation(self) -> None:
        completions = FakeCompletions("OCR result")
        state = OmlxOcrCallState()
        wrapper = OmlxChatCompletions(
            completions,
            omlx_base_url="http://127.0.0.1:8000/v1",
            ocr_call_state=state,
            max_tokens=16384,
            image_max_tokens=768,
            temperature=0,
            repetition_penalty=1.1,
        )

        wrapper.create(
            model="ocr-model",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract text."},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AA=="},
                        },
                    ],
                }
            ],
        )
        self.assertEqual(completions.kwargs["max_tokens"], 768)

        wrapper.create(model="ocr-model", messages=[])
        self.assertEqual(completions.kwargs["max_tokens"], 16384)

    def test_keeps_explicit_lower_image_limit(self) -> None:
        completions = FakeCompletions("OCR result")
        state = OmlxOcrCallState()
        wrapper = OmlxChatCompletions(
            completions,
            omlx_base_url="http://127.0.0.1:8000/v1",
            ocr_call_state=state,
            max_tokens=16384,
            image_max_tokens=768,
            temperature=0,
            repetition_penalty=1.1,
        )

        wrapper.create(
            model="ocr-model",
            messages=[
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:x"}},
                    ]
                }
            ],
            max_tokens=256,
        )
        self.assertEqual(completions.kwargs["max_tokens"], 256)

    def test_discards_degenerate_repeated_output(self) -> None:
        completions = FakeCompletions("筆" * 100, finish_reason="length")
        state = OmlxOcrCallState()

        response = self.create_wrapper(completions, state).create(
            model="ocr-model",
            messages=[],
        )

        self.assertEqual(response.choices[0].message.content, "")
        self.assertEqual(len(state.errors), 1)
        self.assertIn("degenerate OCR output", state.errors[0])

    def test_discards_model_prompt_loop_observed_in_complex_pdf(self) -> None:
        completions = FakeCompletions(
            "toimage.Returnnonextractedtext.Donotaddanytextfromimage. " * 20,
            finish_reason="length",
        )
        state = OmlxOcrCallState()

        response = self.create_wrapper(completions, state).create(
            model="unlimited-ocr-mxfp8-mlx",
            messages=[],
        )

        self.assertEqual(response.choices[0].message.content, "")
        self.assertEqual(state.warning_codes, ["OCR_OUTPUT_DEGENERATED"])
        self.assertTrue(has_ocr_output_anomaly(completions.content))

    def test_allows_structured_ocr_control_tokens_when_not_degenerate(self) -> None:
        text = "<|det|>title [30, 306, 999, 542]<|/det|>SIGNATURE: APPROVED"
        self.assertFalse(has_ocr_output_anomaly(text))

    def test_reports_non_degenerate_truncation(self) -> None:
        completions = FakeCompletions("Recognized text", finish_reason="length")
        state = OmlxOcrCallState()

        response = self.create_wrapper(completions, state).create(
            model="ocr-model",
            messages=[],
        )

        self.assertEqual(response.choices[0].message.content, "Recognized text")
        self.assertEqual(len(state.errors), 1)
        self.assertIn("output limit", state.errors[0])

    def test_trims_repetitive_loop_output(self) -> None:
        completions = FakeCompletions(
            "正常识别内容" + "重复循环输出片段" * 5,
            finish_reason="length",
        )
        state = OmlxOcrCallState()

        response = self.create_wrapper(completions, state).create(
            model="ocr-model",
            messages=[],
        )

        self.assertEqual(
            response.choices[0].message.content,
            "正常识别内容" + "重复循环输出片段",
        )
        self.assertEqual(len(state.errors), 1)
        self.assertIn("repetitive OCR output", state.errors[0])

    def test_repetitive_loop_detection_and_trim(self) -> None:
        self.assertTrue(has_repetitive_loop("前缀" + "重复循环输出片段" * 4))
        self.assertFalse(has_repetitive_loop("普通文本内容"))
        self.assertEqual(
            trim_repetitive_loop("前缀" + "重复循环输出片段" * 4),
            "前缀" + "重复循环输出片段",
        )

    def test_call_state_provider_isolates_requests(self) -> None:
        completions = FakeCompletions("OCR result")
        first_state = OmlxOcrCallState()
        second_state = OmlxOcrCallState()
        states = iter((first_state, second_state))
        wrapper = OmlxChatCompletions(
            completions,
            omlx_base_url="http://127.0.0.1:8000/v1",
            call_state_provider=lambda: next(states),
            max_tokens=4096,
            temperature=0,
            repetition_penalty=1.1,
        )

        wrapper.create(model="ocr-model", messages=[])
        wrapper.create(model="ocr-model", messages=[])

        self.assertEqual(first_state.request_count, 1)
        self.assertEqual(second_state.request_count, 1)


if __name__ == "__main__":
    unittest.main()
