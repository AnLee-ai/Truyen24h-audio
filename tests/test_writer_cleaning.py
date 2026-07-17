import unittest
import sys
import os

# Add src to python path to allow imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.writer import remove_repetitive_sentences

class TestWriterCleaning(unittest.TestCase):
    
    def test_remove_repetitive_sentences_consecutive_dup(self):
        text = "Trần Lam đi quét lá thông. Trần Lam đi quét lá thông. Cậu cảm thấy mỏi mệt."
        expected = "Trần Lam đi quét lá thông. Cậu cảm thấy mỏi mệt."
        result = remove_repetitive_sentences(text)
        self.assertEqual(result.strip(), expected.strip())
        
    def test_remove_repetitive_sentences_case_insensitive(self):
        text = "Trần Lam đi quét lá thông. trần lam đi quét lá thông. Cậu cảm thấy mỏi mệt."
        expected = "Trần Lam đi quét lá thông. Cậu cảm thấy mỏi mệt."
        result = remove_repetitive_sentences(text)
        self.assertEqual(result.strip(), expected.strip())

    def test_remove_repetitive_paragraphs(self):
        text = "Đoạn văn thứ nhất.\n\nĐoạn văn thứ nhất.\n\nĐoạn văn thứ hai."
        expected = "Đoạn văn thứ nhất.\n\nĐoạn văn thứ hai."
        result = remove_repetitive_sentences(text)
        self.assertEqual(result.strip(), expected.strip())

if __name__ == '__main__':
    unittest.main()
