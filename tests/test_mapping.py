import unittest

from leantex.build import _attribute_messages
from leantex.models import LeanMessage, SnippetRange


class MappingTests(unittest.TestCase):
    def test_attributes_by_line_range(self) -> None:
        ranges = [
            SnippetRange(index=1, start_line=3, end_line=5),
            SnippetRange(index=2, start_line=8, end_line=10),
        ]
        messages = [
            LeanMessage(severity="info", text="ok", line=4, col=1),
            LeanMessage(severity="error", text="bad", line=9, col=2),
            LeanMessage(severity="warning", text="global", line=20, col=1),
        ]

        by_snippet, global_messages = _attribute_messages(ranges, messages)

        self.assertEqual(len(by_snippet[1]), 1)
        self.assertEqual(len(by_snippet[2]), 1)
        self.assertEqual(len(global_messages), 1)


if __name__ == "__main__":
    unittest.main()
