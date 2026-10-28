"""Solution-PDF key extraction. Run from api/: python -m unittest tests.test_solution_key"""
from __future__ import annotations

import unittest

import fitz

try:
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient
except Exception:  # httpx is only needed to exercise the HTTP routes
    TestClient = None

from main import app
from omr.classify import colour_role
from omr.key_parse import parse_answer_key
from omr.solution_key import SolutionKeyError, extract_key_from_pdf, extract_key_from_text


def _pdf_lines(lines: list[str], font: str = "helv") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        if y > 780:
            page = doc.new_page()
            y = 72
        page.insert_text((72, y), line, fontsize=12, fontname=font)
        y += 18
    data = doc.tobytes()
    doc.close()
    return data


def _pdf_table(letters: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "MC Answers", fontsize=14, fontname="helv")
    for i, letter in enumerate(letters):
        col = i % 10
        row = i // 10
        x = 72 + col * 46
        y = 100 + row * 40
        page.insert_text((x, y), str(i + 1), fontsize=11, fontname="helv")
        page.insert_text((x, y + 16), letter, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


class ParseTextTests(unittest.TestCase):
    def test_numbered_lines_and_case(self):
        text = "\n".join(
            [
                "F.6 Uniform Test",
                "Paper 2 MC Answers",
                "1. C",
                "2. D",
                "3. A",
                "4. b",
                "5. (C)",
                "6) A",
                "7. Answer: D",
                "8. D [1]",
            ]
        )
        got = extract_key_from_text(text)
        self.assertEqual(got.key, ["C", "D", "A", "B", "C", "A", "D", "D"])
        self.assertFalse(got.partial)
        self.assertEqual(got.review, [])

    def test_inline_pairs_and_glued(self):
        got = extract_key_from_text("1. C   2. D   3. A   4. B   5. C\n6A 7B 8C 9D 10A")
        self.assertEqual(got.n, 10)
        self.assertEqual(got.key, list("CDABCABCD A".replace(" ", "")))
        self.assertFalse(got.partial)

    def test_space_separated_columns(self):
        text = "1 C  11 A  21 B\n2 D  12 C  22 A\n3 A  13 D  23 C\n4 B  14 B  24 D"
        got = extract_key_from_text(text)
        self.assertEqual(got.key[0], "C")
        self.assertEqual(got.key[10], "A")
        self.assertEqual(got.key[20], "B")
        self.assertEqual(got.key[23], "D")
        self.assertEqual(got.n, 24)
        # Holes between the three columns stay blank for the teacher.
        self.assertIn(5, got.review)
        self.assertEqual(got.key[4], "")
        self.assertTrue(got.partial)

    def test_number_row_letter_row(self):
        text = "Answers\n1 2 3 4 5 6 7 8 9 10\nC D A B A C D B A C"
        got = extract_key_from_text(text)
        self.assertEqual(got.key, list("CDABA CDBAC".replace(" ", "")))
        self.assertFalse(got.partial)

    def test_chinese_heading_and_fullwidth(self):
        got = extract_key_from_text("選擇題答案\n１．Ｃ\n２．Ｄ\n３．Ａ\n第4題：B")
        self.assertEqual(got.key, ["C", "D", "A", "B"])
        self.assertFalse(got.partial)

    def test_unnumbered_list_is_flagged_not_silent(self):
        got = extract_key_from_text("Answer key:\nC D A B C")
        self.assertEqual(got.key, ["C", "D", "A", "B", "C"])
        self.assertTrue(got.partial)
        self.assertEqual(got.review, [1, 2, 3, 4, 5])

    def test_conflict_is_blank(self):
        got = extract_key_from_text("1. C\n2. D\n3. A\n4. B\n1. D")
        self.assertEqual(got.key[0], "")
        self.assertEqual(got.key[1:], ["D", "A", "B"])
        self.assertIn(1, got.review)
        self.assertTrue(got.partial)

    def test_missing_question_is_blank(self):
        got = extract_key_from_text("1. C\n2. D\n4. B\n5. A")
        self.assertEqual(got.key, ["C", "D", "", "B", "A"])
        self.assertEqual(got.review, [3])

    def test_prose_and_subparts_are_not_a_key(self):
        prose = (
            "1. The value of x is shown in figure 2. Option A is incorrect because\n"
            "the graph crosses the axis. Question 3 refers to part (a) of the stem.\n"
            "2024 Paper 1A\n"
            "Therefore students should review chapter 4.\n"
        )
        with self.assertRaises(SolutionKeyError):
            extract_key_from_text(prose)

    def test_subparts_ignored_when_real_key_present(self):
        text = "Section B\n1. (a) Find x.\n2. (b) Hence find y.\nAnswers\n1. C\n2. D\n3. A\n4. B"
        got = extract_key_from_text(text)
        self.assertEqual(got.key, ["C", "D", "A", "B"])
        self.assertFalse(got.partial)

    def test_two_line_answer(self):
        got = extract_key_from_text("1.\nAnswer: C\n2.\n(D)\n3.\nA\n4.\nB")
        self.assertEqual(got.key, ["C", "D", "A", "B"])

    def test_stray_high_number_dropped(self):
        lines = [f"{i}. {('ABCD'[i % 4])}" for i in range(1, 11)]
        lines.append("45. B")
        got = extract_key_from_text("\n".join(lines))
        self.assertEqual(got.n, 10)
        self.assertNotIn(45, got.review)
        self.assertEqual(len(got.key), 10)

    def test_class_name_1a_is_not_a_key(self):
        with self.assertRaises(SolutionKeyError):
            extract_key_from_text("Paper 1A\nClass 1A\n2024")


class ParsePdfTests(unittest.TestCase):
    def test_numbered_pdf(self):
        data = _pdf_lines(["Paper 2 MC Answers", "1. C", "2. D", "3. A", "4. b"])
        got = extract_key_from_pdf(data)
        self.assertEqual(got.key, ["C", "D", "A", "B"])
        self.assertEqual(got.source, "pdf-text")

    def test_table_pdf(self):
        letters = "CDABACDBACBDCABADCBACDBACDBACD"
        got = extract_key_from_pdf(_pdf_table(letters))
        self.assertEqual("".join(got.key), letters)
        self.assertFalse(got.partial)
        self.assertEqual(got.review, [])

    def test_chinese_pdf(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "選擇題答案", fontsize=14, fontname="china-t")
        page.insert_text((72, 100), "1. C", fontsize=12, fontname="china-t")
        page.insert_text((72, 122), "2. D", fontsize=12, fontname="china-t")
        page.insert_text((72, 144), "3. A", fontsize=12, fontname="china-t")
        data = doc.tobytes()
        doc.close()
        got = extract_key_from_pdf(data)
        self.assertEqual(got.key, ["C", "D", "A"])

    def test_scan_without_text_is_an_error(self):
        doc = fitz.open()
        page = doc.new_page()
        page.draw_rect(fitz.Rect(80, 80, 200, 140), color=(0, 0, 0), fill=(0, 0, 0))
        data = doc.tobytes()
        doc.close()
        with self.assertRaises(SolutionKeyError) as ctx:
            extract_key_from_pdf(data)
        self.assertIn("不會猜測", str(ctx.exception))

    def test_prose_pdf_does_not_invent(self):
        data = _pdf_lines(
            [
                "1. The value of x is shown in figure 2. Option A is incorrect because",
                "the graph crosses the axis. Question 3 refers to part (a) of the stem.",
                "2024 Paper 1A",
                "Therefore students should review chapter 4.",
            ]
        )
        with self.assertRaises(SolutionKeyError):
            extract_key_from_pdf(data)


@unittest.skipUnless(TestClient is not None, "httpx is required for API tests")
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_parse_pdf_and_text(self):
        pdf = _pdf_lines(["1. C", "2. D", "3. A", "1. B"])
        res = self.client.post("/api/parse-key", files={"pdf": ("sol.pdf", pdf, "application/pdf")})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["n"], 3)
        self.assertEqual(body["key"][0], "")
        self.assertIn(1, body["review"])
        self.assertTrue(body["partial"])
        self.assertEqual(body["key"][1:], ["D", "A"])

        text = self.client.post("/api/parse-key", data={"answer_key": "1A 2b 3C"})
        self.assertEqual(text.status_code, 200, text.text)
        self.assertEqual(text.json()["key"], ["A", "B", "C"])
        self.assertFalse(text.json()["partial"])

    def test_parse_rejects_empty_and_prose(self):
        empty = self.client.post("/api/parse-key", data={"answer_key": "  "})
        self.assertEqual(empty.status_code, 400)
        prose = _pdf_lines(
            [
                "1. The value of x is shown in figure 2. Option A is incorrect because",
                "students should review the whole chapter before answering.",
                "2024 Paper 1A is not an answer key.",
            ]
        )
        bad = self.client.post(
            "/api/parse-key", files={"pdf": ("notes.pdf", prose, "application/pdf")}
        )
        self.assertEqual(bad.status_code, 422)
        self.assertIn("不會猜測", bad.json()["detail"])

    def test_mark_still_returns_xlsx(self):
        doc = fitz.open()
        doc.new_page()
        scan = doc.tobytes()
        doc.close()
        res = self.client.post(
            "/api/mark",
            data={"answer_key": "1A 2B 3C", "exam_name": "Demo"},
            files={"pdf": ("scan.pdf", scan, "application/pdf")},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("spreadsheet", res.headers["content-type"])
        self.assertTrue(res.content.startswith(b"PK"))
        self.assertEqual(res.headers["X-CLSNP-Questions"], "3")

    def test_scoring_accepts_lower_b(self):
        self.assertEqual(colour_role("b", "OK", "B"), "green")
        self.assertEqual(parse_answer_key("1C 2d 3A"), ["C", "D", "A"])


if __name__ == "__main__":
    unittest.main()
