import unittest
from types import SimpleNamespace

from integrations.omlx import OmlxChatCompletions, OmlxOcrCallState


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
