"""OCR evidence boxes. No network: Vision responses are faked."""

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

from backend.extraction import extractor
from backend.extraction.locate import LocateError, Word, locate, locate_after, parse_words
from backend.extraction.vision import GoogleVisionOCR
from backend.preprocessing.image import ProcessedImage, to_original_bbox
from backend.tests.test_nicrron_extraction import FakeGateway, entry, primary_reply, SECONDARY

# Demo B's prescription line, as OCR returns it.
LINE = [
    Word("Metoprolol", (539, 904, 760, 946)),
    Word("tartrate", (775, 904, 1010, 946)),
    Word("15mg", (1045, 900, 1150, 948)),
    Word("tab", (1180, 905, 1260, 946)),
]
SIG = [Word("Sig:", (510, 1032, 600, 1074)), Word("1", (620, 1032, 640, 1074)),
       Word("tab", (660, 1032, 740, 1074)), Word("po", (760, 1032, 810, 1074)), Word("bid", (830, 1032, 900, 1074))]
WORDS = LINE + SIG


def test_strength_box_lands_on_the_strength_not_the_drug():
    # The model's box covered the end of "tartrate".
    assert locate("15 mg", WORDS, hint=(935, 908, 1020, 942)) == (1045, 900, 1150, 948)


def test_multi_word_value_gets_one_box_around_its_words():
    assert locate("Metoprolol tartrate", WORDS) == (539, 904, 1010, 946)
    assert locate("1 tab po bid", WORDS) == (620, 1032, 900, 1074)


def test_numbers_must_match_exactly():
    assert locate("15 mg", [Word("10mg", (0, 0, 40, 20))]) is None
    assert locate("NPI 1707981932", [Word("NPI", (0, 0, 30, 20)), Word("1707981932", (35, 0, 150, 20))])
    assert locate("1707981932", [Word("1707981982", (0, 0, 150, 20))]) is None


def test_ocr_misreads_still_match_but_unrelated_text_does_not():
    assert locate("Metoprolol tartrate", [Word("Metopro1ol", (0, 0, 10, 10)), Word("tartrale", (12, 0, 30, 10))])
    assert locate("hydroxyzine", WORDS) is None


def test_runs_never_span_lines():
    # "tab" ends the drug line and "Sig:" starts the next: no box may cover both lines.
    box = locate("tab Sig", WORDS)
    assert box is None or box[3] - box[1] < 60


def test_repeated_text_goes_to_the_occurrence_nearest_the_model_box():
    assert locate("tab", WORDS, hint=(650, 1030, 750, 1070)) == (660, 1032, 740, 1074)
    assert locate("tab", WORDS, hint=(1170, 900, 1270, 950)) == (1180, 905, 1260, 946)


def test_short_values_need_a_nearby_model_box():
    assert locate("1", WORDS) is None  # "1" alone could be anywhere
    assert locate("1", WORDS, hint=(600, 1030, 650, 1070)) == (620, 1032, 640, 1074)
    assert locate("1", WORDS, hint=(100, 100, 120, 120)) is None


def test_parse_words_reads_vision_word_boxes():
    result = {"fullTextAnnotation": {"pages": [{"blocks": [{"paragraphs": [{"words": [
        {"symbols": [{"text": "1"}, {"text": "5"}, {"text": "m"}, {"text": "g"}],
         "boundingBox": {"vertices": [{"x": 10, "y": 5}, {"x": 40, "y": 5}, {"x": 40, "y": 20}, {"x": 10, "y": 20}]}},
        {"symbols": [{"text": "x"}], "boundingBox": {"vertices": [{"x": 1}]}},  # malformed: skipped
    ]}]}]}]}}
    assert parse_words(result) == [Word("15mg", (10, 5, 40, 20))]
    assert parse_words({}) == []


@pytest.mark.parametrize("angle", [-1.0, 0.0, 3.0])
def test_box_on_the_deskewed_image_maps_back_onto_the_original(angle):
    original = Image.new("L", (800, 1000), 255)
    ImageDraw.Draw(original).rectangle([600, 100, 640, 130], fill=0)
    upscaled = original.resize((1600, 2000)).rotate(angle, fillcolor=255)
    ink = upscaled.point(lambda v: 255 if v < 128 else 0).getbbox()
    processed = ProcessedImage(Path("x.png"), upscaled, upscaled, angle, (800, 1000))
    x0, y0, x1, y1 = to_original_bbox(ink, processed)
    assert abs(x0 - 600) <= 3 and abs(y0 - 100) <= 3 and abs(x1 - 641) <= 3 and abs(y1 - 131) <= 3


class FakeOCR:
    name = "fake-ocr"

    def __init__(self, words=None, error=None):
        self._words, self._error = words or [], error

    def words(self, image):
        if self._error:
            raise self._error
        return self._words


@pytest.fixture
def fax(tmp_path) -> Path:
    path = tmp_path / "fax.png"
    Image.new("L", (1700, 2200), 255).save(path)
    return path


def run(fax, locator):
    primary = primary_reply(strength=entry("15mg", best="15 mg", bbox=[600, 585, 660, 610]))
    gw = FakeGateway({"extract_primary": primary, "extract_secondary": SECONDARY})
    return extractor.extract(fax, "rx_test", gateway=gw, locator=locator)


def test_extractor_uses_the_ocr_box_and_keeps_model_boxes_for_the_rest(fax):
    rx = run(fax, FakeOCR(WORDS))
    assert rx.fields["strength"].evidence.bbox == (1045, 900, 1150, 948)
    assert rx.fields["patient"].evidence.bbox == (155, 154, 464, 201)  # not found by OCR: model box
    assert rx.models["locate"] == "fake-ocr"


def test_ocr_failure_is_recorded_and_model_boxes_are_kept(fax):
    rx = run(fax, FakeOCR(error=LocateError("Vision HTTP 403: API key not valid")))
    assert rx.fields["patient"].evidence.bbox == (155, 154, 464, 201)
    assert any("OCR failed" in e for e in rx.errors)


def test_signature_present_is_never_located(fax):
    rx = run(fax, FakeOCR([Word("yes", (1, 1, 50, 20))]))
    sig = rx.fields.get("signature_present")
    assert sig is None or sig.evidence.bbox != (1, 1, 50, 20)


def test_vision_client_sends_key_in_header_and_fails_closed(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        sent.update(url=url, headers=headers, body=json)
        return httpx.Response(200, content=__import__("json").dumps({"responses": [{"fullTextAnnotation": {"pages": []}}]}),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert GoogleVisionOCR("secret-key").words(Image.new("L", (10, 10), 255)) == []
    assert sent["headers"] == {"X-Goog-Api-Key": "secret-key"} and "secret-key" not in sent["url"]
    assert sent["body"]["requests"][0]["features"] == [{"type": "DOCUMENT_TEXT_DETECTION"}]

    for response in (httpx.Response(403, text="denied"), httpx.Response(200, text="not json"),
                     httpx.Response(200, content=json.dumps({"responses": [{"error": {"message": "bad image"}}]}))):
        monkeypatch.setattr(httpx, "post", lambda *a, r=response, **k: r)
        with pytest.raises(LocateError):
            GoogleVisionOCR("k").words(Image.new("L", (10, 10), 255))


def test_vision_is_off_without_a_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_VISION_API_KEY", raising=False)
    assert GoogleVisionOCR.from_env() is None
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "k")
    assert isinstance(GoogleVisionOCR.from_env(), GoogleVisionOCR)


def test_second_reading_is_tried_when_the_first_is_not_on_the_page(fax):
    words = [Word("100mg", (1045, 900, 1150, 948))]  # OCR agrees with the secondary read, not the primary
    secondary = {"fields": {"drug": entry("hydralazine HCl"), "strength": entry("100mg")}, "other_text": []}
    primary = primary_reply(strength=entry("15mg", best="15 mg", bbox=[600, 585, 660, 610]))
    gw = FakeGateway({"extract_primary": primary, "extract_secondary": secondary})
    rx = extractor.extract(fax, "rx_test", gateway=gw, locator=FakeOCR(words))
    assert rx.fields["strength"].evidence.bbox == (1045, 900, 1150, 948)


FADED = [Word("Metoprolol", (521, 897, 747, 958)), Word("tartrate", (776, 896, 1000, 957)),
         Word("romg", (1039, 896, 1153, 955)), Word("tab", (1201, 895, 1287, 955)),
         Word("10mg", (1300, 1200, 1400, 1250))]  # another strength lower on the page


def test_unreadable_strength_is_found_by_its_unit_after_the_drug():
    # Demo B: OCR read the faded "75mg" as "romg", matching neither model reading.
    assert locate("15 mg", FADED) is None
    assert locate_after("15mg", FADED, (521, 896, 1000, 958)) == (1039, 896, 1153, 955)


def test_unit_search_stays_on_the_drug_line_and_handles_split_words():
    split = [Word("Lisinopril", (100, 100, 300, 140)), Word("2?", (320, 100, 360, 140)), Word("mg", (365, 100, 410, 140))]
    assert locate_after("2? mg", split, (100, 100, 300, 140)) == (320, 100, 410, 140)
    assert locate_after("15 mg", [Word("10mg", (1300, 1200, 1400, 1250))], (521, 896, 1000, 958)) is None
    assert locate_after(None, FADED, (521, 896, 1000, 958)) is None


def test_extractor_finds_a_faded_strength_next_to_the_drug(fax):
    words = [Word("hydroxyzine", (500, 900, 800, 950)), Word("HCl", (810, 900, 880, 950)), Word("romg", (900, 900, 1000, 950))]
    rx = run(fax, FakeOCR(words))
    assert rx.fields["strength"].evidence.bbox == (900, 900, 1000, 950)
    assert list(rx.fields) == [f for f in extractor.EXTRACTED_FIELDS if f in rx.fields]  # order kept
