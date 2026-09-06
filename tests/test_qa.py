import unittest

from pronounceit.qa import audit_pronunciations, load_checklist, load_source_lexicon


class PronunciationQaTests(unittest.TestCase):
    def test_high_yield_checklist_is_substantial(self) -> None:
        self.assertGreaterEqual(len(load_checklist()), 155)

    def test_pronunciation_audit_accepts_complete_bundled_audio(self) -> None:
        audit = audit_pronunciations()
        self.assertTrue(audit.passed, audit.as_dict())
        self.assertGreaterEqual(audit.dictionary_terms, 590)
        self.assertGreaterEqual(audit.checklist_terms, 155)
        self.assertEqual(audit.source_lexicon_terms, 462)
        self.assertEqual(audit.missing_audio_files, [])
        self.assertEqual(audit.excluded_audio_placeholders, 0)
        self.assertEqual(audit.missing_source_lexicon_terms, [])
        self.assertEqual(audit.source_lexicon_pronunciation_mismatches, [])
        self.assertEqual(audit.unsafe_speech_text, [])
        self.assertEqual(sum(audit.quality_tiers.values()), audit.dictionary_terms)
        self.assertEqual(audit.quality_tiers["verified"], 155)
        self.assertEqual(sum(audit.written_quality_counts.values()), audit.dictionary_terms)
        self.assertEqual(audit.missing_syllables, [])
        self.assertEqual(audit.missing_pronunciation, [])
        self.assertEqual(audit.written_data_errors, [])

    def test_source_lexicon_is_substantial_and_parseable(self) -> None:
        entries = load_source_lexicon()

        self.assertEqual(len(entries), 462)
        self.assertIn(("agranulocytosis", "uh-GRAN-yoo-loh-sy-TOH-sis"), entries)
        self.assertIn(("thoracentesis", "thor-uh-sen-TEE-sis"), entries)


if __name__ == "__main__":
    unittest.main()
