import unittest

from chip.selection import SelectionError, parse_selection


class ParseSelectionTest(unittest.TestCase):
    def test_single_and_list(self):
        self.assertEqual(parse_selection("2", 5), [2])
        self.assertEqual(parse_selection("1,3,5", 5), [1, 3, 5])

    def test_ranges_and_whitespace(self):
        self.assertEqual(parse_selection(" 1, 3 - 5 ", 5), [1, 3, 4, 5])

    def test_all(self):
        self.assertEqual(parse_selection("ALL", 3), [1, 2, 3])

    def test_duplicates_removed_and_sorted(self):
        self.assertEqual(parse_selection("3,1,2-3", 5), [1, 2, 3])

    def test_out_of_range(self):
        with self.assertRaisesRegex(SelectionError, "'6'"):
            parse_selection("1,6", 5)

    def test_malformed(self):
        for bad in ("abc", "3-1", "1-", "-2"):
            with self.subTest(bad=bad), self.assertRaises(SelectionError):
                parse_selection(bad, 5)

    def test_empty(self):
        with self.assertRaises(SelectionError):
            parse_selection("  ", 5)

    def test_all_on_empty_list(self):
        with self.assertRaises(SelectionError):
            parse_selection("all", 0)
