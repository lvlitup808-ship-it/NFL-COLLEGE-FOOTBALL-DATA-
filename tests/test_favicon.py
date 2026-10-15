import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_favicon_is_valid_scalable_svg():
    root = ET.parse(ROOT / "app/web/favicon.svg").getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("viewBox") == "0 0 64 64"


def test_pilot_ui_links_and_serves_favicon():
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in (ROOT / "app/web/index.html").read_text()
    # Read the source rather than import app.pilot, which strips legacy routes from the shared app.
    pilot = (ROOT / "app/pilot.py").read_text()
    assert '@app.get("/favicon.svg"' in pilot
    assert '@app.get("/favicon.ico"' in pilot
    assert 'media_type="image/svg+xml"' in pilot
