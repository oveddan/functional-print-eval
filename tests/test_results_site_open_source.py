"""The results site says the eval is open source, where a first-time visitor sees it and in the footer, with a link to
the repository, and what it says about the licence is what the LICENSE file says."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/oveddan/functional-print-eval"


def test_the_page_says_it_is_open_source_in_the_header_and_the_footer():
    page = (ROOT / "scripts/results_site/index.html").read_text()
    header = page[page.index("<header"):page.index("</header>")]
    footer = page[page.index("<footer"):page.index("</footer>")]
    for part in (header, footer):
        assert "open source" in part and "MIT licence" in part and f'href="{REPO}"' in part
    assert header.index("open-source") < header.index('id="finding"')  # before the numbers: on the first screen
    assert f'href="{REPO}/blob/main/LICENSE"' in footer


def test_the_licence_the_page_names_is_the_one_in_the_repository():
    assert (ROOT / "LICENSE").read_text().splitlines()[0].strip() == "MIT License"
