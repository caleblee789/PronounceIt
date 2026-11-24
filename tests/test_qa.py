import json
import unittest

from pronounceit.dictionary import DATA_FILE
from pronounceit.qa import audit_pronunciations


class PronunciationQaTests(unittest.TestCase):
    def test_library_has_complete_audio_and_written_pronunciations(self) -> None:
        audit = audit_pronunciations()
        self.assertTrue(audit.passed, audit.as_dict())
        release = json.loads(DATA_FILE.with_name("audio-pack-release.json").read_text(encoding="utf-8"))
        self.assertEqual(audit.audio_terms, release["assetCount"])
        self.assertEqual(audit.audio_terms, audit.dictionary_terms)
        self.assertEqual(audit.written_terms, audit.dictionary_terms)


if __name__ == "__main__":
    unittest.main()
