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


class LabelSelectionTest(unittest.TestCase):
    LABELS = ["shopbox-api#274", "api#2069", "acme/api#1"]

    def test_labels_map_to_indexes(self):
        self.assertEqual(parse_selection("api#2069, shopbox-api#274", 3, self.LABELS), [1, 2])

    def test_labels_case_insensitive_and_full_name(self):
        self.assertEqual(parse_selection("ACME/API#1", 3, self.LABELS), [3])

    def test_mixed_with_numbers(self):
        self.assertEqual(parse_selection("3,shopbox-api#274", 3, self.LABELS), [1, 3])

    def test_skip_option_ignored(self):
        self.assertEqual(parse_selection("Không chọn, api#2069", 3, self.LABELS), [2])

    def test_unknown_label(self):
        with self.assertRaisesRegex(SelectionError, "'nope#1'"):
            parse_selection("nope#1", 3, self.LABELS)
