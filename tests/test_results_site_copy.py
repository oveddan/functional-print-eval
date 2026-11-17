"""Copy on the results site that a cold read by two other models showed was too absolute or missing a pointer."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "scripts/results_site"
REPO = "https://github.com/oveddan/functional-print-eval"


def test_the_site_never_says_nothing_a_model_designed_was_printed():
    """Round 3 printed six roofs cut from models' Estoa designs, so "nothing a model designed was printed" is false.
    The site says, in the README's words, that no final design was printed, and points to the round."""
    texts = {path.name: path.read_text() for path in [*SITE.glob("*.html"), *SITE.glob("*.js"),
                                                    ROOT / "scripts/results_site.py", ROOT / "scripts/results_site_checks.yaml"]}
    for name, text in texts.items():
        assert "Nothing a model designed was printed" not in text, name
        assert "No model's design was printed" not in text, name
    page = texts["index.html"]
    assert "No final design was printed" in page
    assert "No final design was printed" in (ROOT / "README.md").read_text()
    assert f'href="{REPO}/blob/main/docs/reference.md#the-test-prints-behind-the-checks"' in page


def test_the_page_copies_the_readme_opening_conditions_and_limits():
    """The site's prose is the README's, so the two don't drift: the opening, the questions, the three conditions,
    the limits and the credit."""
    page = (SITE / "index.html").read_text()
    readme = (ROOT / "README.md").read_text()
    for phrase in ("These kinds of prints often involve multiple steps and parts",
                   "Designing and printing these parts is slow.",
                   "Which models are the best at designing functional 3D prints",
                   "Can we know if a 3D design is going to work without actually printing it?",
                   "Do models know what they don't know?",
                   "Given the hardware on hand, can it design multiple parts and the connections between them?",
                   "Trials ran in three conditions, named the same way everywhere in the results:",
                   "the model can ask for measurements and hands in one design, with no feedback.",
                   "the model can ask for small test prints before its final design.",
                   "One printer, one material, one setting.",
                   "Possible bias toward Claude.",
                   "The replies only come from my test prints."):
        assert phrase in readme, phrase
        assert phrase in page, phrase
    assert page.count('Made by <a href="https://danoved.xyz">Dan Oved</a>.') == 2  # under the title and in the footer
    for anchor in ("what-wasnt-graded-and-the-prints-that-would-settle-it", "assumptions-calls-and-known-limits"):
        assert f'href="{REPO}/blob/main/docs/reference.md#{anchor}"' in page


def test_the_site_says_test_print_and_uses_us_spelling():
    for path in [*SITE.glob("*.html"), *SITE.glob("*.js"), *SITE.glob("*.css")]:
        text = path.read_text().replace("aria-labelledby", "")  # the HTML attribute's own spelling
        for word in ("millimetre", "colour", "centre", "labelled", "unrecognised"):
            assert word not in text, (path.name, word)


def test_the_pass_definition_points_at_the_assumptions_and_the_anchor_exists():
    page = (SITE / "index.html").read_text()
    assert f'href="{REPO}/blob/main/docs/reference.md#assumptions-the-verdicts-rest-on"' in page
    assert "### Assumptions the verdicts rest on" in (ROOT / "docs/reference.md").read_text()


def test_the_simulated_person_is_said_to_answer_from_records_or_the_bridge_prediction():
    for path in (ROOT / "scripts/results_site.py", SITE / "detail.js"):
        text = path.read_text()
        assert "only from Dan's recorded test prints." not in text, path.name
        if path.suffix == ".js":  # what a reader sees; the generator's docstring states the exception itself
            assert "answers only from Dan's recorded" not in text, path.name
        assert "the bridge check's" in text, path.name


def test_the_footer_points_to_the_reference_and_to_running_it():
    app = (SITE / "app.js").read_text()
    assert '"/blob/main/docs/reference.md"' in app and '"#run-it"' in app
    assert "## Run it" in (ROOT / "README.md").read_text()
